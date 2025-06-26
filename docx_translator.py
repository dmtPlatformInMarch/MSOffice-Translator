from text_translator import translate
from module import only_allowed_chars
from docx import Document
from docx.table import _Cell

async def docxtrans(input_file_path, output_file_path, from_lang, to_lang) :
    docx = Document(input_file_path)

    for para in docx.paragraphs:
        original_text = para.text.strip()

        if original_text == "" or only_allowed_chars(original_text):
            continue

        translated_text = await translate(original_text, from_lang, to_lang)
        para.text = translated_text

    for table in docx.tables:
        for row in table._tbl.tr_lst:  # lxml element 순회
            for tc in row.tc_lst:
                # 병합된 셀 중복 출력 방지
                if tc.vMerge == 'continue':
                    continue
                cell = _Cell(tc, table)
                text = cell.text.strip()

                if text == "" or only_allowed_chars(text):
                    continue

                text = await translate(cell.text, from_lang, to_lang)
                cell.text = text

    docx.save(output_file_path)