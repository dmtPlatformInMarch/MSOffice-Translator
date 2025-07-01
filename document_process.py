import os
import re
import shutil
from collections import Counter
from typing import List
from urllib.parse import quote, unquote
import uvicorn
import openpyxl
from bs4 import BeautifulSoup
from fastapi import FastAPI, File, UploadFile, Query, Form
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pptx import Presentation
from pathlib import Path
from module import only_allowed_chars
from docx_translator import docxtrans
from text_translator import translate
import threading
from TaskCounter import TaskCounter
from CustomThread import CustomThread

app = FastAPI()

app.add_middleware(CORSMiddleware,
                   allow_origins=["*"],
                   allow_credentials=False,
                   allow_methods=["*"],
                   allow_headers=["*"],
                   )

req_storage_path = "./req_doc"
storage_path = "./translated"
src_lang_list = ["ko", "en"]
tgt_lang_list = ["en", "ko"]
valid_lang_list = ["ko", "en"]


def clean_folders():
    try:
        input_dir = Path("req_doc")
        output_dir = Path("translated")

        for dir_path in [input_dir, output_dir]:
            if dir_path.exists():
                shutil.rmtree(dir_path)
            dir_path.mkdir()

    except Exception as e:
        pass


# [번역전처리] 문장의 non-character 여부 검사
def is_character(sentence):
    pattern = r'[가-힣a-zA-Z0-9]'
    return bool(re.search(pattern, sentence))


def extract_text_with_ids(soup):
    text_elements = []
    element_seq = 1

    for element in soup.find_all(True):  # True means all tags
        if element.name not in ['style', 'meta', 'script']:
            if element.string and element.string.strip():  # Check if element has text
                # Assigning a unique ID
                element_id = f'element_{element_seq}'
                text_elements.append({'id': element_id, 'original_text': element.string.strip(),
                                      'translated_text': element.string.strip(), 'tag': element.name,
                                      'parent': str(element.parent.name)})
                element.string.replace_with(element_id)
                element_seq += 1
    return text_elements


def replace_html_text(soup, sentences):
    for sentence in sentences:
        element = soup.find(True, string=sentence["id"])
        if element and element.string and element.string.strip():
            element.string.replace_with(sentence["translated_text"])
    return soup


def parse_html(html_text, from_lang, to_lang):
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
        translation_results.append(translate(sentence, from_lang, to_lang))

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
def html_translation(input_html, output_html, uuid, from_lang="ko", to_lang="en"):
    uuid_folder_path = os.path.join(req_storage_path, uuid)
    os.makedirs(uuid_folder_path, exist_ok=True)

    with open(os.path.join(uuid_folder_path, input_html), 'r', encoding='utf-8') as file:
        input_html_data = file.read()

    detection_list, output_html_data = parse_html(input_html_data, from_lang, to_lang)
    print("[DL] : ", detection_list)
    counter = Counter(detection_list)
    print(counter)
    most_common = counter.most_common(1)
    # detect_lang = most_common[0][0]

    with open(os.path.join(uuid_folder_path, "html", output_html), 'w', encoding='utf-8') as file:
        file.write(output_html_data)


# [DOCX]
def docx_translation(input_docx, output_docx, uuid, task_counter, from_lang="ko", to_lang="en"):
    uuid_folder_path = os.path.join(req_storage_path, uuid)
    os.makedirs(uuid_folder_path, exist_ok=True)
    uuid_storage_path = os.path.join(storage_path, uuid)
    os.makedirs(uuid_storage_path, exist_ok=True)

    docxtrans(os.path.join(uuid_folder_path, input_docx),
              os.path.join(uuid_storage_path, output_docx),
              from_lang,
              to_lang,
              uuid,
              task_counter)


# [PPTX]
def pptx_translation(input_pptx, output_pptx, uuid, task_counter, from_lang="ko", to_lang="en"):
    uuid_folder_path = os.path.join(req_storage_path, uuid)
    os.makedirs(uuid_folder_path, exist_ok=True)
    uuid_storage_path = os.path.join(storage_path, uuid)
    os.makedirs(uuid_storage_path, exist_ok=True)

    prs = Presentation(os.path.join(uuid_folder_path, input_pptx))

    # 테스크 전체 개수 세기
    task_counter.total_task_count += 1
    for slide in prs.slides:
        for shape in slide.shapes:
            task_counter.total_task_count += 1

    try:
        for slide in prs.slides:
            for shape in slide.shapes:
                if TaskCounter.task_dict[uuid]["task"].stop_event.is_set():
                    raise SystemExit("스레드를 종료합니다.")

                task_counter.completed_task_count += 1

                # 텍스트를 포함하는 도형 수정
                if hasattr(shape, "text"):
                    for paragraph in shape.text_frame.paragraphs:
                        if TaskCounter.task_dict[uuid]["task"].stop_event.is_set():
                            raise SystemExit("스레드를 종료합니다.")

                        translated_text = translate(paragraph.text, from_lang, to_lang)

                        if paragraph.level > 0:
                            try:
                                bullet_style = paragraph.bullet
                                paragraph.text = translated_text
                                paragraph.bullet = bullet_style
                            except:
                                paragraph.text = translated_text
                        else:
                            paragraph.text = translated_text

        prs.save(os.path.join(uuid_storage_path, output_pptx))

        task_counter.completed_task_count += 1

    except SystemExit as e:
        print("번역이 취소되었습니다.")
    except Exception as e:
        print("문서번역 중 예상치 못한 에러가 발생했습니다.")
    finally:
        del TaskCounter.task_dict[uuid]


# [XLSX]
def xlsx_translation(input_xlsx, output_xlsx, uuid, task_counter, from_lang="ko", to_lang="en"):
    try:
        uuid_folder_path = os.path.join(req_storage_path, uuid)
        os.makedirs(uuid_folder_path, exist_ok=True)
        uuid_storage_path = os.path.join(storage_path, uuid)
        os.makedirs(uuid_storage_path, exist_ok=True)

        workbook = openpyxl.load_workbook(os.path.join(uuid_folder_path, input_xlsx))

        # 전체 테스크 개수 셈
        task_counter.total_task_count += 1
        for sheet in workbook.sheetnames:
            worksheet = workbook[sheet]
            task_counter.total_task_count += worksheet.max_column * worksheet.max_row

        for sheet in workbook.sheetnames:
            worksheet = workbook[sheet]
            for row in worksheet.iter_rows():
                for cell in row:
                    if TaskCounter.task_dict[uuid]["task"].stop_event.is_set():
                        raise SystemExit("스레드를 종료합니다.")

                    if isinstance(cell.value, str) and cell.value.strip():
                        translated_text = translate(cell.value, from_lang, to_lang)
                        cell.value = translated_text

                    task_counter.completed_task_count += 1

        workbook.save(os.path.join(uuid_storage_path, output_xlsx))

        task_counter.completed_task_count += 1

    except SystemExit as e:
        print("번역이 취소되었습니다.")
    except Exception as e:
        print(f"문서번역 중 예상치 못한 에러가 발생했습니다. : {repr(e)}")
    finally:
        del TaskCounter.task_dict[uuid]


# [TXT]
def txt_translation(input_txt, output_txt, uuid, task_counter, from_lang="ko", to_lang="en"):
    try:
        uuid_folder_path = os.path.join(req_storage_path, uuid)
        os.makedirs(uuid_folder_path, exist_ok=True)
        uuid_storage_path = os.path.join(storage_path, uuid)
        os.makedirs(uuid_storage_path, exist_ok=True)

        with open(os.path.join(uuid_folder_path, input_txt), 'r', encoding='utf-8') as file:
            lines = file.readlines()

        # (파일까지 저장하고 나서 100%로 만들려고 +1을 함.)
        task_counter.total_task_count = len(lines) + 1

        for i in range(len(lines)):
            if TaskCounter.task_dict[uuid]["task"].stop_event.is_set():
                raise SystemExit("스레드를 종료합니다.")

            task_counter.completed_task_count += 1

            text = lines[i].strip()
            if text == "" or only_allowed_chars(text):
                continue

            lines[i] = translate(text, from_lang, to_lang)

        with open(os.path.join(uuid_storage_path, output_txt), 'w', encoding='utf-8') as new_file:
            new_file.writelines(lines)

        task_counter.completed_task_count += 1

    except SystemExit as e:
        print("번역이 취소되었습니다.")
    except Exception as e:
        print("문서번역 중 예상치 못한 에러가 발생했습니다.")
    finally:
        del TaskCounter.task_dict[uuid]


# [파일 번역 처리]
def run_document_translation(uuid, input_file, task_counter, src="ko", tgt="en"):
    _, file_ext = os.path.splitext(input_file)
    output_filename = input_file

    if file_ext == '.html':
        html_translation(input_file, output_filename, uuid, src, tgt)
    elif file_ext == '.txt':
        txt_translation(input_file, output_filename, uuid, task_counter, src, tgt)
    elif file_ext == '.docx':
        docx_translation(input_file, output_filename, uuid, task_counter, src, tgt)
    elif file_ext == ".pptx":
        pptx_translation(input_file, output_filename, uuid, task_counter, src, tgt)
    elif file_ext == ".xlsx":
        xlsx_translation(input_file, output_filename, uuid, task_counter, src, tgt)


@app.get("/ping")
async def pong():
    json_compatible_data = jsonable_encoder({'response': "pong"})
    return JSONResponse(json_compatible_data)


@app.post("/trans_file")
async def trans_file(uuid: str = Form(...), from_lang: str = Form(...),
                     to_lang: str = Form(...), files: List[UploadFile] = File(...)):
    try:
        for file in files:
            filename = file.filename

            uuid_folder_path = os.path.join(req_storage_path, uuid)
            req_file_path = os.path.join(uuid_folder_path, filename)
            os.makedirs(uuid_folder_path, exist_ok=True)

            uuid_storage_path = os.path.join(storage_path, uuid)
            os.makedirs(uuid_storage_path, exist_ok=True)

            # 파일 저장
            with open(req_file_path, "wb") as buffer:
                buffer.write(await file.read())

            task_counter = TaskCounter()
            TaskCounter.task_dict[uuid] = {"task": None, "counter": task_counter}
            stop_event = threading.Event()
            thread = threading.Thread(target=run_document_translation,
                                      args=(uuid, filename, task_counter, from_lang, to_lang),
                                      daemon=False)
            thread.start()
            TaskCounter.task_dict[uuid]["task"] = CustomThread(thread, stop_event)

        return JSONResponse(content={"task": "processing"}, status_code=200)

    except Exception as e:
        return JSONResponse(content={"message": "Internal server error"}, status_code=500)


@app.get("/download/{file_name}")
async def download_file(file_name: str, uuid: str = Query(...)):
    try:
        file_name = unquote(file_name)
        uuid_storage_path = os.path.join(storage_path, uuid)
        file_path = os.path.join(uuid_storage_path, file_name)

        if os.path.exists(file_path):
            return FileResponse(file_path, media_type='application/octet-stream')
        else:
            return JSONResponse(content={"error": "File not found."}, status_code=404)

    except Exception as e:
        return JSONResponse(content={"message": "Internal server error"}, status_code=500)


@app.get("/progress")
def get_progress(uuid: str):
    try:
        task_obj = TaskCounter.task_dict.get(uuid)

        if not task_obj:
            task_obj = {"counter": TaskCounter(-1, -1)}
        return JSONResponse(status_code=200, content={
            "data": {"completed_tasks": task_obj["counter"].completed_task_count,
                     "total_tasks": task_obj["counter"].total_task_count}})

    except Exception as e:
        return JSONResponse(content={"message": "Internal server error"}, status_code=500)


@app.get("/complete/{filename}")
def complete(filename: str, uuid: str):
    filename = unquote(filename)

    try:
        file_path = Path(os.path.join(os.path.join(storage_path, uuid), filename))

        if not file_path.exists():
            return JSONResponse(status_code=404, content={"detail": "File not found"})

        file_size = file_path.stat().st_size
        detect_lang = "nn"

        result = {
            "data": {
                "filename": filename,
                "size": file_size,
                "detect_lang": detect_lang,
                "file": f"/download/{quote(filename)}"
            }
        }

        return JSONResponse(status_code=200, content=result)

    except Exception as e:
        return JSONResponse(content={"message": "Internal server error"}, status_code=500)


@app.delete("/cancel")
def cancel_trans(uuid: str):
    try:
        task_obj = TaskCounter.task_dict.get(uuid)

        if task_obj:
            task_obj["task"].stop()

        return JSONResponse(status_code=200, content={"message": "The task has already been completed or deleted."})

    except Exception as e:
        return JSONResponse(content={"message": "Internal server error"}, status_code=500)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=6446)
