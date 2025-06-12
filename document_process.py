import os
import re
import shutil
import traceback
from collections import Counter
from typing import List
from urllib.parse import unquote

import uvicorn
import aiohttp
import fitz, pymupdf
import openpyxl
from bs4 import BeautifulSoup
from docx import Document
from fastapi import FastAPI, File, UploadFile, Query, Form
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pptx import Presentation

app = FastAPI()

# CORS 설정
# Add CORS middleware to allow all origins and headers
# noinspection PyTypeChecker
app.add_middleware(CORSMiddleware, allow_origins=["*"],  # Allows all origins
    allow_credentials=False, allow_methods=["*"],  # Allows all HTTP methods
    allow_headers=["*"],  # Allows all headers
)

textflags = fitz.TEXT_INHIBIT_SPACES | fitz.TEXT_DEHYPHENATE | fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_MEDIABOX_CLIP | fitz.TEXT_CID_FOR_UNKNOWN_UNICODE
ts_url = "http://dilato-webtrans-nmt-patent:7979"
req_storage_path = "./req_doc"
storage_path = "./translated"
src_lang_list = ["ko", "en"]
tgt_lang_list = ["en", "ko"]
valid_lang_list = ["ko", "en"]


# [번역전처리] 문장의 non-character 여부 검사
def is_character(sentence):
    pattern = r'[가-힣a-zA-Z0-9]'
    return bool(re.search(pattern, sentence))


# [번역] source language => target language 번역 API
# return dict() => { 'detect_lang', 'result' }
async def translate(text, src, tgt):
    """
    lines = text.split("\n")
    headers = { "Content-Type": "application/json" }
    lines_gather = []
    detect_lang = src
    try:
        for line in lines:
            if line == "":
                lines_gather.append(line)
                continue
            data = { "text": line, "from_lang": src, "to_lang": tgt }
            async with aiohttp.ClientSession() as session:
                async with session.post(ts_url + "/translation", headers=headers, json=data) as response:
                    resp_json = await response.json()
                    res = resp_json.get('result')
                    detect_lang = res['detect_lang']
                    line_gather.append(res['result'])
        results = { 'detect_lang': detect_lang, 'result': '\n'.join(lines_gather) }
        return results
    except:
        traceback.print_exc()
        return None
detect_lang = ["en", "ko", "en", "auto"]"""
    headers = {"Content-Type": "application/json"}
    data = {"text": text, "from_lang": src, "to_lang": tgt}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(ts_url + "/translation", headers=headers, json=data) as response:
                resp_json = await response.json()
                return resp_json.get('result')
    except:
        traceback.print_exc()
        return None


# [번역] batch 단위의 다중 번역
# async def batch_translate(texts, from_lang="ko", to_lang="en"):
#     url = ts_url + "/translation-bulk"
#     req_headers = {'Content-Type': 'application/json'}
#     translations = []
#
#     for i in range(0, len(texts), 50):
#         chunk = texts[i:i + 50]
#         formatted_texts = list(map(lambda t: t["original_text"], chunk))
#
#         data = {"from_lang": from_lang, "to_lang": to_lang, "texts": formatted_texts}
#
#         try:
#             async with aiohttp.ClientSession() as session:
#                 async with session.post(url, headers=req_headers, json=data) as response:
#                     resp_json = await response.json()
#                     translations.extend(
#                         resp_json)  # res = requests.post(url, headers=req_headers, data=json.dumps(data))  # if res.status_code == 200:  #	translations.extend(res.json())
#         except:
#             traceback.print_exc()
#             return None
#     return translations


def extract_text_with_ids(soup):
    text_elements = []
    element_seq = 1

    for element in soup.find_all(True):  # True means all tags
        if element.name not in ['style', 'meta', 'script']:
            if element.string and element.string.strip():  # Check if element has text
                # Assigning a unique ID
                element_id = f'element_{element_seq}'
                text_elements.append({'id': element_id, 'original_text': element.string.strip(),
                    'translated_text': element.string.strip(), 'tag': element.name, 'parent': str(element.parent.name)})
                element.string.replace_with(element_id)
                element_seq += 1
    return text_elements


def replace_html_text(soup, sentences):
    for sentence in sentences:
        element = soup.find(True, string=sentence["id"])
        if element and element.string and element.string.strip():
            element.string.replace_with(sentence["translated_text"])
    return soup


async def parse_html(html_text, from_lang, to_lang):
    detection_list = []
    # BeautifulSoup을 사용하여 HTML 파싱
    html_text = html_text.replace("<br/>", " ")
    html_text = html_text.replace("<br />", " ")
    html_text = html_text.replace("<br>", " ")
    soup = BeautifulSoup(html_text, 'html.parser')
    soup = BeautifulSoup(soup.prettify(), 'html.parser')

    sentences = extract_text_with_ids(soup)
    translation_results = []
    for sentence in sentences:
        translation_results.append(await translate(sentence, from_lang, to_lang))

    if translation_results:
        for i, result in enumerate(translation_results):
            sentences[i]["translated_text"] = result["translations"]
            detection_list.append(result["detect_lang"])
        soup = replace_html_text(soup, sentences)
        translated_html_text = str(soup)
        return detection_list, translated_html_text
    else:
        detection_list = ["nn"]

    return detection_list, html_text


# [HTML]
async def html_translation(input_html, output_html, uuid, from_lang="ko", to_lang="en"):
    # uuid
    uuid_folder_path = os.path.join(req_storage_path, uuid)
    os.makedirs(uuid_folder_path, exist_ok=True)

    with open(os.path.join(uuid_folder_path, input_html), 'r', encoding='utf-8') as file:
        input_html_data = file.read()

    detection_list, output_html_data = await parse_html(input_html_data, from_lang, to_lang)
    print("[DL] : ", detection_list)
    counter = Counter(detection_list)
    print(counter)
    most_common = counter.most_common(1)
    detect_lang = most_common[0][0]

    with open(os.path.join(uuid_folder_path, "html", output_html), 'w', encoding='utf-8') as file:
        file.write(output_html_data)

    return detect_lang, output_html


# [DOCX]
async def docx_translation(input_docx, output_docx, uuid, from_lang="ko", to_lang="en"):
    # uuid
    uuid_folder_path = os.path.join(req_storage_path, uuid)
    os.makedirs(uuid_folder_path, exist_ok=True)
    uuid_storage_path = os.path.join(storage_path, uuid)
    os.makedirs(uuid_storage_path, exist_ok=True)

    docx = Document(os.path.join(uuid_folder_path, input_docx))
    detect_lang = from_lang

    for para in docx.paragraphs:
        for run in para.runs:
            original_text = run.text
            if original_text.strip():
                translated_text = await translate(original_text, from_lang, to_lang)
                detect_lang = translated_text["detect_lang"]
                run.text = translated_text["result"]
    docx.save(os.path.join(uuid_storage_path, "docx", output_docx))
    return detect_lang, output_docx


# [PDF]
async def pdf_translation(input_pdf, output_pdf, uuid, from_lang="ko", to_lang="en"):
    # uuid
    uuid_folder_path = os.path.join(req_storage_path, uuid)
    os.makedirs(uuid_folder_path, exist_ok=True)

    doc: pymupdf.Document = fitz.open(os.path.join(uuid_folder_path, input_pdf))
    ocg_xref = doc.add_ocg("Translation", on=True)
    detect_lang = from_lang

    for item in doc.get_layers(): print(item)

    text_width = 0
    margin = {'left': 0, 'top': 0, 'right': 0, 'bottom': 0}

    for page_num in range(doc.page_count):
        page = doc[page_num]
        tp = page.get_textpage()

        blocks = page.get_text("blocks", textpage=tp, flags=textflags)
        text_boxes = page.get_text("dict")["blocks"]
        # 페이지 사이즈 구하는 함수
        if text_boxes:
            content_rect = fitz.Rect(min(box["bbox"][0] for box in text_boxes),  # 왼쪽
                min(box["bbox"][1] for box in text_boxes),  # 위쪽
                max(box["bbox"][2] for box in text_boxes),  # 오른쪽
                max(box["bbox"][3] for box in text_boxes)  # 아래쪽
            )
            margin['left'] = content_rect.x0 - page.rect.x0
            margin['top'] = content_rect.y0 - page.rect.y0
            margin['right'] = page.rect.x1 - content_rect.x1
            margin['bottom'] = page.rect.y1 - content_rect.y1

            text_width = page.rect.width - margin['left'] - margin['right']
        # 블럭 단위 처리방식
        for block in blocks:
            # 텍스트 정보 추출
            bbox = block[:4]
            x0, y0, x1, y1 = bbox
            page.draw_rect(bbox, color=None, fill=(1, 1, 1), oc=ocg_xref)
            original_text = block[4]
            # print("original_text: ", original_text)
            merged_text = ""
            # 구분선 처리
            if re.search(r"—{5,}", original_text):
                continue
            page.draw_rect(bbox, color=None, fill=(1, 1, 1), oc=ocg_xref)
            if original_text != "":
                translated_res = await translate(original_text, from_lang, to_lang)
                if translated_res:
                    detect_lang = translated_res["detect_lang"]
                    translated_text = translated_res["result"]
                else:
                    detect_lang = from_lang
                    translated_text = original_text
                merged_text += translated_text
                # print("merged_text : ", merged_text)
                merged_text_length = fitz.get_text_length(merged_text, fontname="helv")
                if merged_text_length > (x1 - x0):
                    new_x1 = x0 + merged_text_length
                    if new_x1 - x0 > text_width and text_width != 0:
                        new_x1 = text_width + x0
                    new_rect = fitz.Rect(x0, y0, new_x1, y1)
                    page.draw_rect(new_rect, color=None, fill=(1, 1, 1), oc=ocg_xref)
                    page.insert_htmlbox(new_rect, merged_text, oc=ocg_xref)
                else:
                    page.insert_htmlbox(bbox, merged_text, oc=ocg_xref)
    doc.subset_fonts()
    doc.ez_save(os.path.join(uuid_folder_path, "pdf", output_pdf))
    doc.close()
    return detect_lang, output_pdf


# [PPTX]
async def pptx_translation(input_pptx, output_pptx, uuid, from_lang="ko", to_lang="en"):
    # uuid
    uuid_folder_path = os.path.join(req_storage_path, uuid)
    os.makedirs(uuid_folder_path, exist_ok=True)
    uuid_storage_path = os.path.join(storage_path, uuid)
    os.makedirs(uuid_storage_path, exist_ok=True)

    prs = Presentation(os.path.join(uuid_folder_path, input_pptx))
    detect_lang = from_lang

    for slide in prs.slides:
        for shape in slide.shapes:
            # 텍스트를 포함하는 도형 수정
            if hasattr(shape, "text"):
                for paragraph in shape.text_frame.paragraphs:
                    translated_text = await translate(paragraph.text, from_lang, to_lang)
                    detect_lang = translated_text["detect_lang"]
                    translated_text = translated_text["result"]
                    if translated_text is None or translated_text == "":
                        continue
                    if paragraph.level > 0:
                        try:
                            bullet_style = paragraph.bullet
                            paragraph.text = translated_text
                            paragraph.bullet = bullet_style
                        except:
                            paragraph.text = translated_text
                    else:
                        paragraph.text = translated_text
    prs.save(os.path.join(uuid_storage_path, "pptx", output_pptx))
    return detect_lang, output_pptx


# [XLSX]
async def xlsx_translation(input_xlsx, output_xlsx, uuid, from_lang="ko", to_lang="en"):
    # uuid
    uuid_folder_path = os.path.join(req_storage_path, uuid)
    os.makedirs(uuid_folder_path, exist_ok=True)
    uuid_storage_path = os.path.join(storage_path, uuid)
    os.makedirs(uuid_storage_path, exist_ok=True)

    # Load xlsx sheet
    workbook = openpyxl.load_workbook(os.path.join(uuid_folder_path, input_xlsx))
    detect_lang = from_lang

    for sheet in workbook.sheetnames:
        worksheet = workbook[sheet]
        for row in worksheet.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value.strip():
                    translated_text = await translate(cell.value, from_lang, to_lang)
                    detect_lang = translated_text["detect_lang"]
                    cell.value = translated_text["result"]
    workbook.save(os.path.join(uuid_storage_path, "xlsx", output_xlsx))
    return detect_lang, output_xlsx


# [TXT]
async def txt_translation(input_txt, output_txt, uuid, from_lang="ko", to_lang="en"):
    # uuid
    uuid_folder_path = os.path.join(req_storage_path, uuid)
    os.makedirs(uuid_folder_path, exist_ok=True)
    uuid_storage_path = os.path.join(storage_path, uuid)
    os.makedirs(uuid_storage_path, exist_ok=True)

    detect_lang = from_lang
    with open(os.path.join(uuid_folder_path, input_txt), 'r', encoding='utf-8') as file:
        data = file.read()

    translated_data = await translate(data, from_lang, to_lang)
    # print("td : ", translated_data)
    detect_lang = translated_data["detect_lang"]
    # print("detect_lang : ", detect_lang)
    translated_data = translated_data["result"]

    with open(os.path.join(uuid_storage_path, "txt", output_txt), 'w', encoding='utf-8') as new_file:
        new_file.write(translated_data)

    return detect_lang, output_txt


# [파일 번역 처리]
async def run_document_translation(uuid, input_file, src="ko", tgt="en"):
    _, file_ext = os.path.splitext(input_file)
    output_filename = "translated_" + input_file

    # html file ts
    if file_ext == '.html':
        return await html_translation(input_file, output_filename, uuid, src, tgt)

    # txt file ts
    if file_ext == '.txt':
        return await txt_translation(input_file, output_filename, uuid, src, tgt)

    # other file ts (docx, pdf, pptx, xlsx)
    if file_ext == '.docx':
        return await docx_translation(input_file, output_filename, uuid, src, tgt)
    elif file_ext == ".pdf":
        return await pdf_translation(input_file, output_filename, uuid, src, tgt)
    elif file_ext == ".pptx":
        return await pptx_translation(input_file, output_filename, uuid, src, tgt)
    elif file_ext == ".xlsx":
        return await xlsx_translation(input_file, output_filename, uuid, src, tgt)
    else:
        return None


# [서버통신확인용]
@app.get("/ping")
async def pong():
    json_compatible_data = jsonable_encoder({'response': "pong"})
    return JSONResponse(json_compatible_data)


# [파일 번역 요청] Query문을 이용하여 사용 (format, filename)
@app.post("/trans_file")
async def trans_file(uuid: str = Form(...), from_lang: str = Form(...), to_lang: str = Form(...),
        files: List[UploadFile] = File(...)):
    result = []
    detect_lang = from_lang

    # print(f"[INIT REQUEST] {from_lang} / {to_lang}")

    for file in files:
        filename = file.filename
        _, text_format = os.path.splitext(filename)
        text_format = text_format[1:]

        decoded_filename = unquote(filename)
        uuid_folder_path = os.path.join(req_storage_path, uuid)
        req_file_path = os.path.join(uuid_folder_path, filename)
        os.makedirs(uuid_folder_path, exist_ok=True)

        uuid_storage_path = os.path.join(storage_path, uuid)
        os.makedirs(uuid_storage_path, exist_ok=True)

        with open(req_file_path, "wb") as buffer:
            buffer.write(await file.read())

        detect_lang, output_filename = await run_document_translation(uuid, filename, from_lang, to_lang)

        print(f"[DETECT LANGUAGE] req ({from_lang}) -> {detect_lang}")

        if detect_lang in valid_lang_list:
            if output_filename is None:
                result.append({'detect_lang': detect_lang, 'filename': "Error", 'size': "0", 'file': "None",
                    'error': "File's ext is not available (av: txt, pdf, docx, pptx, xlsx)"})
            else:
                translated_file_path = os.path.join(uuid_storage_path, f"{text_format}/{output_filename}")
                translated_file_size = os.path.getsize(translated_file_path)

                result.append({'detect_lang': detect_lang, 'filename': output_filename, 'size': translated_file_size,
                    'file': f"/download/{uuid}/{output_filename}"})
        else:
            result.append({'detect_lang': detect_lang, 'filename': "Error", 'size': "0", 'file': "None",
                'error': "Invalid language code request. Please check the detect_lang, or request's language code."})

    result = jsonable_encoder(result)
    return JSONResponse(content={"result": result}, status_code=200)


# [번역된 파일 엔드포인트] API를 호출하여 파일 엔드포인트 접근
@app.get("/download/{file_name}")
async def download_file(file_name: str, uuid: str = Query(...)):
    _, file_ext = os.path.splitext(file_name)
    file_ext = file_ext[1:]
    uuid_storage_path = os.path.join(storage_path, uuid)
    file_path = os.path.join(uuid_storage_path, f"{file_ext}/{file_name}")
    if os.path.exists(file_path):
        return FileResponse(file_path, media_type='application/octet-stream')
    else:
        return JSONResponse(content={"error": "File not found."}, status_code=404)


# [파일 존재 여부 확인]
@app.get("/check_file")
async def check_file(uuid: str = Query(...), filename: str = Query(...)):
    uuid_storage_path = os.path.join(storage_path, uuid)
    target_file_name = f"translated_{filename}"
    target_file_path = os.path.join(uuid_storage_path, target_file_name)

    if os.path.exists(target_file_path):
        return JSONResponse(content={"exists": True, "path": target_file_path}, status_code=200)
    else:
        return JSONResponse(content={"exists": False, "path": "None"}, status_code=404)


# [작업 완료 후 삭제 요청] UUID 기반 폴더 삭제 엔드포인트
@app.delete("/delete_file")
async def delete_file(uuid: str = Query(...)):
    uuid_folder_path = os.path.join(req_storage_path, uuid)
    uuid_storage_path = os.path.join(storage_path, uuid)

    # 여기에 해당 폴더 경로 체크 후 삭제
    for path in [uuid_folder_path, uuid_storage_path]:
        if os.path.exists(path):
            try:
                shutil.rmtree(path)  # 여기 코드 부분에서 삭제 시도 중에 권한 에러가 날 수 있어요~
            except Exception as e:
                return JSONResponse(content={"error": f"Failed to delete {path}: {str(e)}"}, status_code=500)
    return JSONResponse(content={"detail": f"Delete '{uuid}' Folder."}, status_code=201)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
