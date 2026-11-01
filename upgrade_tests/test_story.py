"""Story contract tests. All provider operations are mocked; no keys are read."""
from copy import deepcopy
import json
from unittest.mock import Mock

import pytest

from upgrade import providers, story


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(providers.requests, 'request', Mock(side_effect=AssertionError('Live API forbidden')))


@pytest.fixture
def source():
    return [
        {'id': 's1', 'start': 0, 'end': 8, 'source': 'We tested 12 filters, you know.'},
        {'id': 's2', 'start': 8, 'end': 16, 'source': 'Only one filter removed the stain in cold water.'},
        {'id': 's3', 'start': 16, 'end': 24, 'source': 'The successful filter cost $5.'},
    ]


@pytest.fixture
def facts():
    return {'facts': [
        {'id': 'f1', 'text': 'The team tested 12 filters.', 'source_ids': ['s1']},
        {'id': 'f2', 'text': 'Only one filter removed the stain in cold water.', 'source_ids': ['s2']},
        {'id': 'f3', 'text': 'The successful filter cost $5.', 'source_ids': ['s3']},
    ], 'takeaways': [{'text': 'A $5 filter removed the stain in cold water.', 'fact_ids': ['f2', 'f3']}]}


@pytest.fixture
def slots():
    return [{'id': 'h', 'start': 0, 'end': 3, 'role': 'hook'},
            {'id': 'c', 'start': 5, 'end': 10, 'role': 'conflict'},
            {'id': 'p', 'start': 17, 'end': 20, 'role': 'punchline'}]


@pytest.fixture
def draft():
    texts = ['Twelve filters. One clean result.',
             'Only one filter removed the stain in cold water.',
             'The winning filter cost $5.']
    return {'segments': [
        {'id': identifier, 'role': role, 'translation': text, 'tts_text': text, 'fact_ids': refs}
        for identifier, role, text, refs in zip(
            ['h', 'c', 'p'], ['hook', 'conflict', 'punchline'], texts,
            [['f1', 'f2'], ['f2'], ['f2', 'f3']])
    ]}


@pytest.fixture
def api(monkeypatch):
    models = Mock(return_value=['test-model'])
    request = Mock()
    monkeypatch.setattr(providers, 'models', models)
    monkeypatch.setattr(providers, 'request', request)
    return models, request


CFG = {'base': 'https://example.invalid/v1', 'model': 'test-model', 'key': 'unused-mock-value'}


def response(data):
    return Mock(json=Mock(return_value={'choices': [{'message': {'content': json.dumps(data)}}]}))


def test_two_calls_preserve_source_and_separate_rewrite_input(source, facts, slots, draft, api):
    original = deepcopy(source)
    models, request = api
    request.side_effect = [response(facts), response(draft)]
    runner = Mock()
    extracted = story.extract_facts(source, 'A practical demonstration', CFG, runner)
    result = story.write_story(extracted, slots, 'For an English-speaking audience', CFG, runner)
    assert source == original
    assert extracted == facts
    assert len(result) == 3
    assert request.call_count == 2
    assert models.call_count == 2
    first = json.loads(request.call_args_list[0].args[4]['messages'][1]['content'])
    second_request = request.call_args_list[1].args[4]
    second = json.loads(second_request['messages'][1]['content'])
    assert first['source_transcript'][0] == {'id': 's1', 'text': source[0]['source']}
    assert 'source_transcript' not in second
    assert source[0]['source'] not in json.dumps(second)
    assert second['facts'] == facts['facts']
    assert second['takeaways'] == facts['takeaways']
    assert second['slots'][0]['max_words'] == 7
    assert second_request['response_format'] == {'type': 'json_object'}
    assert request.call_args.kwargs['runner'] is runner
    assert runner.check.call_count == 2


def test_story_round_trip_derives_provenance_and_keeps_slot_order(facts, slots, draft):
    original = deepcopy((facts, slots, draft))
    draft['segments'].reverse()
    result = story.validate_story(draft, facts, slots)
    assert [row['id'] for row in result] == ['h', 'c', 'p']
    assert result[0]['source_ids'] == ['s1', 's2']
    assert result[0]['source'] == ' '.join(f['text'] for f in facts['facts'][:2])
    assert all(row['lock_end'] is True and row['mode'] == 'story' for row in result)
    assert story.validate_story({'segments': result}, facts, slots) == result
    assert story.validate_story(result, facts, slots) == result
    assert facts == original[0] and slots == original[1]


def test_facts_validation_does_not_mutate_source_or_fact_bundle(source, facts):
    before = deepcopy((source, facts))
    normalized = story.validate_facts(facts, source)
    normalized['facts'][0]['source_ids'].append('s3')
    assert (source, facts) == before


@pytest.mark.parametrize('kind', ['missing_fact_id', 'duplicate_fact_id', 'unknown_source',
                                 'duplicate_source_ref', 'missing_source_ref', 'empty_fact',
                                 'missing_fact_array', 'empty_takeaways', 'unknown_takeaway_ref',
                                 'empty_takeaway', 'duplicate_takeaway_ref', 'nan_extra', 'nonobject'])
def test_rejects_invalid_facts(kind, source, facts):
    if kind == 'missing_fact_id':
        facts['facts'][0].pop('id')
    elif kind == 'duplicate_fact_id':
        facts['facts'][1]['id'] = 'f1'
    elif kind == 'unknown_source':
        facts['facts'][0]['source_ids'] = ['not-in-transcript']
    elif kind == 'duplicate_source_ref':
        facts['facts'][0]['source_ids'] = ['s1', 's1']
    elif kind == 'missing_source_ref':
        facts['facts'][0]['source_ids'] = []
    elif kind == 'empty_fact':
        facts['facts'][0]['text'] = '  '
    elif kind == 'missing_fact_array':
        facts.pop('facts')
    elif kind == 'empty_takeaways':
        facts['takeaways'] = []
    elif kind == 'unknown_takeaway_ref':
        facts['takeaways'][0]['fact_ids'] = ['unknown']
    elif kind == 'empty_takeaway':
        facts['takeaways'][0]['text'] = ''
    elif kind == 'duplicate_takeaway_ref':
        facts['takeaways'][0]['fact_ids'] = ['f2', 'f2']
    elif kind == 'nan_extra':
        facts['ignored'] = float('nan')
    else:
        facts = []
    with pytest.raises(providers.ProviderError):
        story.validate_facts(facts, source)


@pytest.mark.parametrize('kind', ['missing_id', 'duplicate_id', 'empty_text', 'nan_time', 'partial_time'])
def test_source_validation_precedes_provider_call(kind, source, api):
    if kind == 'missing_id':
        source[0].pop('id')
    elif kind == 'duplicate_id':
        source[1]['id'] = 's1'
    elif kind == 'empty_text':
        source[0]['source'] = ''
    elif kind == 'nan_time':
        source[0]['start'] = float('nan')
    else:
        source[0].pop('end')
    with pytest.raises(providers.ProviderError):
        story.extract_facts(source, '', CFG, None)
    assert not api[0].called and not api[1].called


@pytest.mark.parametrize('kind', ['duplicate_id', 'missing_id', 'unknown_id', 'wrong_role',
                                 'unknown_fact', 'duplicate_fact', 'empty_fact_refs',
                                 'empty_subtitle', 'empty_tts', 'too_many_subtitle_words',
                                 'too_many_tts_words', 'changed_start', 'changed_end',
                                 'nan_time', 'infinite_extra', 'unlocked', 'changed_mode',
                                 'changed_source', 'changed_source_ids', 'invented_number'])
def test_rejects_invalid_story(kind, facts, slots, draft):
    row = draft['segments'][0]
    if kind == 'duplicate_id':
        draft['segments'][1]['id'] = 'h'
    elif kind == 'missing_id':
        row.pop('id')
    elif kind == 'unknown_id':
        row['id'] = 'unknown'
    elif kind == 'wrong_role':
        row['role'] = 'punchline'
    elif kind == 'unknown_fact':
        row['fact_ids'] = ['unknown']
    elif kind == 'duplicate_fact':
        row['fact_ids'] = ['f1', 'f1']
    elif kind == 'empty_fact_refs':
        row['fact_ids'] = []
    elif kind == 'empty_subtitle':
        row['translation'] = ' '
    elif kind == 'empty_tts':
        row['tts_text'] = ''
    elif kind == 'too_many_subtitle_words':
        row['translation'] = 'one two three four five six seven eight'
    elif kind == 'too_many_tts_words':
        row['tts_text'] = 'one two three four five six seven eight'
    elif kind == 'changed_start':
        row['start'] = .5
    elif kind == 'changed_end':
        row['end'] = 4
    elif kind == 'nan_time':
        row['end'] = float('nan')
    elif kind == 'infinite_extra':
        row['ignored'] = float('inf')
    elif kind == 'unlocked':
        row['lock_end'] = False
    elif kind == 'changed_mode':
        row['mode'] = 'translation'
    elif kind == 'changed_source':
        row['source'] = 'Invented evidence'
    elif kind == 'changed_source_ids':
        row['source_ids'] = ['s3']
    else:
        row['tts_text'] = 'They tested 99 filters.'
    with pytest.raises(providers.ProviderError):
        story.validate_story(draft, facts, slots)


@pytest.mark.parametrize('kind', ['overlap', 'nan', 'duplicate_id', 'missing_id', 'wrong_hook',
                                 'wrong_role', 'too_short', 'missing_punchline'])
def test_invalid_slots_rejected_before_api(kind, facts, slots, api):
    if kind == 'overlap':
        slots[1]['start'] = 2
    elif kind == 'nan':
        slots[1]['end'] = float('nan')
    elif kind == 'duplicate_id':
        slots[1]['id'] = 'h'
    elif kind == 'missing_id':
        slots[1].pop('id')
    elif kind == 'wrong_hook':
        slots[0]['end'] = 2
    elif kind == 'wrong_role':
        slots[1]['role'] = 'hook'
    elif kind == 'too_short':
        slots[1]['end'] = 5.1
    else:
        slots.pop()
    with pytest.raises(providers.ProviderError):
        story.write_story(facts, slots, '', CFG, None)
    assert not api[0].called and not api[1].called


def test_invalid_fact_bundle_rejected_before_api(facts, slots, api):
    facts['takeaways'][0]['fact_ids'] = ['missing']
    with pytest.raises(providers.ProviderError):
        story.write_story(facts, slots, '', CFG, None)
    assert not api[0].called and not api[1].called


def test_unused_facts_allowed_and_multiple_conflict_slots_allowed(facts, slots, draft):
    facts['facts'].append({'id': 'unused', 'text': 'Extra supported context.', 'source_ids': ['s4']})
    slots.insert(2, {'id': 'c2', 'start': 11, 'end': 15, 'role': 'conflict'})
    draft['segments'].insert(2, {**draft['segments'][1], 'id': 'c2'})
    assert len(story.validate_story(draft, facts, slots)) == 4


def test_budget_boundary_and_float_rounding(facts, slots, draft):
    slots[1]['end'] = 9.799999999999999
    draft['segments'][1]['tts_text'] = 'one two three four five six seven eight nine ten eleven twelve'
    assert story.story_prompt(facts, slots)['slots'][1]['max_words'] == 12
    assert story.validate_story(draft, facts, slots)
    draft['segments'][1]['tts_text'] += ' thirteen'
    with pytest.raises(providers.ProviderError, match='budget'):
        story.validate_story(draft, facts, slots)


def test_story_payload_drops_cached_transcript_and_extra_model_fields(facts, slots):
    facts['source_transcript'] = [{'id': 's1', 'source': 'FORBIDDEN ORIGINAL WORDING'}]
    facts['facts'][0]['raw_source'] = 'FORBIDDEN ORIGINAL WORDING'
    facts['takeaways'][0]['source_quote'] = 'FORBIDDEN ORIGINAL WORDING'
    payload = story.story_prompt(facts, slots)
    assert 'FORBIDDEN ORIGINAL WORDING' not in json.dumps(payload)
    assert set(payload) == {'language', 'editorial_context', 'facts', 'takeaways', 'slots'}


@pytest.mark.parametrize('content', ['not json', '[]', '{}',
                                    '{"facts":[],"facts":[],"takeaways":[]}',
                                    '{"facts":NaN,"takeaways":[]}',
                                    '{"facts":Infinity,"takeaways":[]}',
                                    '{"facts":1e999,"takeaways":[]}'])
def test_malformed_json_rejected_without_content_leak(content, source, api):
    api[1].return_value = Mock(json=Mock(return_value={
        'choices': [{'message': {'content': content}}]}))
    with pytest.raises(providers.ProviderError) as error:
        story.extract_facts(source, '', CFG, None)
    assert CFG['key'] not in str(error.value)


@pytest.mark.parametrize('envelope', [{}, {'choices': []}, {'choices': [{'message': {'content': None}}]}])
def test_malformed_completion_envelope(envelope, source, api):
    api[1].return_value = Mock(json=Mock(return_value=envelope))
    with pytest.raises(providers.ProviderError):
        story.extract_facts(source, '', CFG, None)


def test_unknown_model_does_not_send_completion(source, api):
    api[0].return_value = ['some-other-model']
    with pytest.raises(providers.ProviderError, match='Model ID'):
        story.extract_facts(source, '', CFG, None)
    api[1].assert_not_called()


def test_prompt_contract_covers_factual_challenge_and_supported_punchline():
    assert 'no real conflict' in story.STORY_INSTRUCTIONS
    assert 'factual challenge' in story.STORY_INSTRUCTIONS
    assert 'punchline must be supported' in story.STORY_INSTRUCTIONS
    assert 'slots are natural pauses' in story.STORY_INSTRUCTIONS
    assert 'independent of narration timing' in story.STORY_INSTRUCTIONS
    assert 'no fixed percentage of time reserved' in story.STORY_INSTRUCTIONS
    assert 'never promise moderation or detection evasion' in story.STORY_INSTRUCTIONS
    assert 'Context may help identify the topic but is not evidence' in story.EXTRACTION_INSTRUCTIONS
