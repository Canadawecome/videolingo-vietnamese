"""Reviewable fact-to-script authoring in the existing local UI."""
import streamlit as st
from . import narration, story
from .store import read, save, digest


def editor(job, info, context, llm, start):
    source=read(job/'source_segments.json')
    if source is None:
        source=read(job/'segments.json',[])
        if narration.is_story(source):
            st.error('Thiếu transcript gốc. Nhập lại SRT nguồn trước khi viết kịch bản.')
            return
        save(job/'source_segments.json',source)
    st.caption('Trích dữ kiện → duyệt → viết tiếng Anh trực tiếp. Không dịch qua ngôn ngữ trung gian. Nội dung mới cần giữ đúng dữ kiện nguồn; không có điểm “nguyên bản 100%” tự động.')
    with st.expander('Transcript nguồn được giữ riêng'):
        st.dataframe(source)
    if st.button('1 · Trích Facts & Key Takeaways (gọi API)',disabled=not source):
        def extract(r):
            facts=story.extract_facts(source,context,llm,r)
            save(job/'story_facts.json',facts)
            save(job/'story_facts_meta.json',{'source_hash':digest(source)})
        start('Trích dữ kiện từ transcript',extract)
    facts=read(job/'story_facts.json')
    facts_ok=False
    if facts:
        st.write('Dữ kiện có dẫn ID câu nguồn')
        fact_rows=st.data_editor(facts['facts'],disabled=['id','source_ids'],key=f'facts_{job.name}_{digest(facts)}')
        takeaways=st.data_editor(facts['takeaways'],disabled=['fact_ids'],key=f'takeaways_{job.name}_{digest(facts)}')
        st.caption('Kiểm tra lại tên, số liệu và kết luận bằng nguồn; ID chỉ giúp truy ngược, không tự chứng minh dữ kiện đúng.')
        if st.button('Lưu & duyệt dữ kiện'):
            try:
                if read(job/'story_facts_meta.json',{}).get('source_hash')!=digest(source):
                    raise ValueError('Transcript nguồn đã đổi; trích lại dữ kiện trước khi duyệt.')
                facts=story.validate_facts({'facts':fact_rows,'takeaways':takeaways},source)
                save(job/'story_facts.json',facts)
                save(job/'story_facts_approval.json',{'signature':narration.facts_signature(source,facts)})
                st.rerun()
            except Exception as e:
                st.error(str(e))
        facts_ok=read(job/'story_facts_approval.json',{}).get('signature')==narration.facts_signature(source,facts)
        if facts_ok:
            st.success('Đã duyệt phiên bản dữ kiện này.')
    st.write('Lịch Hook → Conflict → Punchline')
    st.caption('Tiếng gốc 40% là mức âm lượng, chỉnh ở tab Giọng & xuất. Lịch này không chia video theo tỷ lệ 60/40.')
    if st.button('Tạo / đặt lại lịch lời đọc'):
        try:
            save(job/'story_slots.json',narration.make_slots(info['duration']))
            st.rerun()
        except ValueError as e:
            st.error(str(e))
    slots=read(job/'story_slots.json',[])
    if not slots:
        st.caption('Hook 0–3 giây; phần giữa triển khai câu chuyện; punchline ở cuối. Có thể chỉnh mốc để dành chỗ cho tiếng động cần nhấn.')
        return
    edited_slots=st.data_editor(slots,disabled=['id','role'],key=f'slots_{job.name}_{digest(slots)}')
    if st.button('Lưu lịch đã chỉnh'):
        try:
            narration.validate_slots(edited_slots,info['duration'])
            save(job/'story_slots.json',edited_slots)
            st.rerun()
        except Exception as e:
            st.error(str(e))
    original=narration.complement([(s['start'],s['end']) for s in slots],info['duration'])
    with st.expander('Khoảng nghỉ tùy chọn giữa lời đọc'):
        st.dataframe(original)
        st.caption('Nguồn có thể còn lời thoại hoặc nhạc. Có thể dùng stem nền đã chuẩn bị ở tab Giọng & xuất.')
    if st.button('2 · Viết Hook → Conflict → Punchline (gọi API)',disabled=not facts_ok):
        def write(r):
            narration.validate_slots(slots,info['duration'])
            result=story.write_story(facts,slots,context,llm,r)
            save(job/'story_draft.json',result)
            save(job/'story_draft_meta.json',{'facts_hash':digest(facts),'slots_hash':digest(slots),'source_hash':digest(source)})
        start('Viết kịch bản tiếng Anh từ dữ kiện đã duyệt',write)
    draft=read(job/'story_draft.json')
    if draft:
        st.caption('Conflict là trở ngại/thách thức có căn cứ; punchline là câu kết mạnh nhưng không bịa thêm kết quả. Sửa hai cột caption và lời đọc nếu cần.')
        edited=st.data_editor(draft,disabled=['id','start','end','role','source','source_ids','fact_ids','mode','lock_end'],key=f'draft_{job.name}_{digest(draft)}')
        if st.button('3 · Lưu & duyệt kịch bản để tạo giọng'):
            try:
                expected={'facts_hash':digest(facts),'slots_hash':digest(slots),'source_hash':digest(source)}
                if read(job/'story_draft_meta.json')!=expected:
                    raise ValueError('Nguồn/dữ kiện/lịch đã đổi; viết lại kịch bản theo phiên bản mới.')
                if not facts_ok:
                    raise ValueError('Duyệt dữ kiện trước khi duyệt kịch bản.')
                checked=story.validate_story({'segments':edited},facts,slots)
                save(job/'story_draft.json',checked)
                save(job/'segments.json',checked)
                save(job/'story_script_approval.json',{'signature':narration.script_signature(job,checked)})
                st.success('Đã áp dụng kịch bản tiếng Anh. Sang Giọng & xuất để tạo Bella và chỉnh âm lượng nền.')
            except Exception as e:
                st.error(str(e))
    if st.button('Khôi phục transcript nguồn làm nội dung đang dùng'):
        save(job/'segments.json',source)
        st.rerun()
