"""Local interview-by-interview pseudonymization and name restoration."""
import io
import re
import streamlit as st
import pandas as pd
from docx import Document
from sanitizer_core import read_transcript, find_suggestions, apply_rules, restore_text
from session_store import list_sessions, new_session, save_session, load_session, validate_rules

st.set_page_config(page_title='Interview Sanitizer', page_icon='🔒', layout='wide')
TOOLS = {'GitHub','GitLab','Microsoft Teams','Teams','Jira','Confluence','SharePoint','Microsoft 365','Azure','AWS','Python','Power BI','ServiceNow','Splunk','Docker','Kubernetes','Terraform','ChatGPT','Copilot','Microsoft','Google','Zoom','Slack','Okta'}
COLUMNS = ['Original','Category','Replacement','Action']

@st.cache_resource(show_spinner=False)
def load_nlp():
    try:
        import spacy
        return spacy.load('en_core_web_sm'), None
    except Exception as exc:
        return None, str(exc)


def docx_bytes(text):
    doc=Document()
    for line in text.split('\n'):
        doc.add_paragraph(line)
    stream=io.BytesIO(); doc.save(stream)
    return stream.getvalue()


def set_editor_rows(rows):
    st.session_state.rows = validate_rules(rows)
    st.session_state.editor_version = st.session_state.get('editor_version',0)+1

st.title('🔒 Interview Sanitizer — independent sessions')
st.caption('Runs locally · review-first · separate saved rules for every interview · restore names into AI output')
st.warning('Pseudonymization is not classification downgrading. Review all outputs before sending to any AI tool and use only workplace-approved services.')

st.subheader('1. Select or create an interview')
sessions=list_sessions()
with st.form('create'):
    name=st.text_input('New interview name (e.g. Cyber Assessment — Interview 01)')
    create=st.form_submit_button('Create separate interview')
if create:
    try:
        sid=new_session(name)
        st.session_state.active_session=sid
        st.session_state.loaded_session=None
        st.rerun()
    except ValueError as exc: st.error(str(exc))

ids=[s['id'] for s in sessions]
if not ids:
    st.info('Create an interview above to begin.')
    st.stop()
active=st.session_state.get('active_session')
if active not in ids: active=ids[0]
active=st.selectbox('Interview session', ids, index=ids.index(active), format_func=lambda x: next(s['title']+' ('+x+')' for s in sessions if s['id']==x))
st.session_state.active_session=active

if st.session_state.get('loaded_session')!=active:
    data=load_session(active)
    st.session_state.rows=data['rules']
    st.session_state.loaded_session=active
    st.session_state.editor_version=st.session_state.get('editor_version',0)+1
    st.session_state.pop('source_text',None)
    st.session_state.pop('source_file_key',None)
    st.session_state.pop('ai_input_key',None)

data=load_session(active)
st.success('Current interview: '+data['title']+' · '+active+' — its rules never apply to other interviews.')

mode=st.radio('Mode', ['Anonymize transcript','Restore names in AI output'], horizontal=True)
if mode=='Anonymize transcript':
    st.subheader('2. Supply this interview transcript')
    file=st.file_uploader('Upload .txt, .vtt or .docx', type=['txt','vtt','docx'], key='transcript_'+active)
    pasted=st.text_area('Or paste transcript',height=140,key='paste_'+active)
    try:
        text=read_transcript(file.name,file.getvalue()) if file else pasted
    except Exception as exc:
        st.error(f'Unable to read file: {exc}'); text=''
    st.subheader('3. Review replacement rules for THIS interview')
    st.write('Add Phoenix Project → Project_A as a new table row. Use **Keep** for technologies such as GitHub. Nothing is replaced unless you select **Replace**.')
    if st.button('Find additional names with spaCy',disabled=not text.strip()):
        model,error=load_nlp()
        if error:
            st.error('spaCy model unavailable. Run: python -m spacy download en_core_web_sm')
        else:
            try:
                found=find_suggestions(text,model,TOOLS)
                previous=validate_rules(st.session_state.rows)
                known={r['Original'].casefold() for r in previous}
                extra=[r for r in found if r['Original'].casefold() not in known]
                set_editor_rows(previous+extra)
                st.info(f'Added {len(extra)} new suggestions. Prior Keep/Replace decisions are unchanged.')
            except ValueError as exc:st.error(str(exc))
    editor=st.data_editor(pd.DataFrame(st.session_state.rows,columns=COLUMNS),num_rows='dynamic',hide_index=True,key=f'editor_{active}_{st.session_state.editor_version}',use_container_width=True,column_config={
        'Original':st.column_config.TextColumn('Original term'),
        'Category':st.column_config.TextColumn('Category'),
        'Replacement':st.column_config.TextColumn('Replace with'),
        'Action':st.column_config.SelectboxColumn('Action',options=['Review','Keep','Replace'],required=True)})
    rows=editor.fillna('').to_dict('records')
    # Save is deliberate; never automatically store another interview's live edits.
    if st.button('Save these rules to this interview',type='primary'):
        try:
            rules=validate_rules(rows)
            save_session(active,data['title'],rules)
            set_editor_rows(rules)
            st.success('Rules saved for this interview only. Note: stored locally as plaintext JSON, not encrypted.')
        except ValueError as exc:st.error(str(exc))
    st.subheader('4. Preview and export this interview')
    if text.strip():
        try:
            sanitized,count=apply_rules(text,validate_rules(rows))
            st.info(f'{count} replacements. Preview always starts from the original text, not an earlier output.')
            left,right=st.columns(2)
            left.text_area('Original excerpt',text[:5000],height=250,disabled=True)
            right.text_area('Pseudonymized excerpt',sanitized[:5000],height=250,disabled=True)
            st.download_button('Download pseudonymized TXT',sanitized.encode('utf-8'),f'{active}_sanitized.txt',mime='text/plain')
            st.download_button('Download pseudonymized DOCX (text-only)',docx_bytes(sanitized),f'{active}_sanitized.docx',mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        except ValueError as exc:st.error(str(exc))
else:
    st.subheader('2. Restore names using ONLY this interview mapping')
    st.write('First select the same interview used to anonymize the AI input. Paste or upload the AI-generated summary. Rules must have been saved in the Anonymize tab.')
    original_file=st.file_uploader('Upload AI output (.txt, .vtt, .docx)',type=['txt','vtt','docx'],key='ai_file_'+active)
    paste=st.text_area('Or paste AI output',height=200,key='ai_paste_'+active)
    try:
        source=read_transcript(original_file.name,original_file.getvalue()) if original_file else paste
    except Exception as exc:
        st.error(str(exc));source=''
    if source.strip():
        try:
            restored,count=restore_text(source,data['rules'])
            st.info(f'{count} placeholders restored using {active} only. AI may alter placeholders; review all names and claims.')
            st.text_area('Restored preview',restored[:12000],height=250,disabled=True)
            st.download_button('Download restored TXT',restored.encode('utf-8'),f'{active}_restored.txt',mime='text/plain')
            st.download_button('Download restored DOCX (text-only)',docx_bytes(restored),f'{active}_restored.docx',mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        except ValueError as exc:st.error(str(exc))

st.divider()
st.caption('Rules are stored in private_sessions/<interview ID>/rules.json on this computer. These files contain real names, are NOT encrypted, and must never go to GitHub. No transcript is automatically saved to disk by the app. Avoid publicly hosting Streamlit.')
