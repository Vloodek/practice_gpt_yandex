from fastapi import FastAPI, Request, Query, HTTPException,File,UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
import aiohttp
import os
import asyncio
from database.database import database, engine, metadata, DATABASE_URL
from database.models import users, sessions,generation_history
from databases import Database
import json
import aiofiles
import shutil
import logging
import datetime
from collections import deque, defaultdict
import validators
import csv

# Очередь пользователей
queue = deque()
processing_user = None
# Настройка логирования
logging.basicConfig(filename='http_requests.log', level=logging.INFO)

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

database = Database(DATABASE_URL)

# Статусы запросов пользователей
user_status = defaultdict(lambda: "В очереди")

lock = asyncio.Lock()

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    logging.info(f"HTTP GET request to /: {request.client.host}")
    session_token = request.cookies.get("session_token")
    query = select(sessions).where(sessions.c.token == session_token)
    session = await database.fetch_one(query)
    return templates.TemplateResponse("index.html", {"request": request, "session": session})

@app.get("/form-page", response_class=HTMLResponse)
async def form_page(request: Request):
    logging.info(f"HTTP GET request to /form-page: {request.client.host}")
    session_token = request.cookies.get("session_token")
    if not session_token:
        return HTMLResponse(content="<script>window.location.href = '/';</script>", status_code=401)
    query = select(sessions).where(sessions.c.token == session_token)
    session = await database.fetch_one(query)
    if not session:
        return HTMLResponse(content="<script>window.location.href = '/';</script>", status_code=401)
    return templates.TemplateResponse("form.html", {"request": request, "session": session})


@app.get("/callback")
async def callback(request: Request):
    return HTMLResponse("""
    <html>
        <body>
            <script>
                function getTokenFromUrl() {
                    const hash = window.location.hash.substring(1);
                    const params = new URLSearchParams(hash);
                    return params.get("access_token");
                }
                const token = getTokenFromUrl();
                if (token) {
                    fetch('/process_token?token=' + encodeURIComponent(token))
                        .then(response => response.text())
                        .then(data => {
                            console.log("Token processed, sending message to main window");
                            if (window.opener) {
                                window.opener.parent.location.reload()
                                window.close();
                            } else {
                                console.error('No opener window found.');
                            }
                            console.log(window.location.origin);
                        })
                        .catch(error => {
                            console.log('Error sending token:', error);
                            window.close();
                        });
                } else {
                    document.body.innerHTML = 'Token not received';
                    window.close();
                }
            </script>
        </body>
    </html>
    """)

@app.get("/process_token", response_class=HTMLResponse)
async def process_token(token: str = Query(None)):
    if token is None:
        print("Token not received")
        return HTMLResponse("Token not received", status_code=400)
    
    print(f"Received token: {token}")

    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://login.yandex.ru/info",
            headers={"Authorization": f"OAuth {token}"}
        ) as response:
            print(f"Yandex response status: {response.status}")
            if response.status != 200:
                error_detail = await response.text()
                print(f"Authentication failed: {error_detail}")
                raise HTTPException(status_code=response.status, detail="Authentication failed")
            user_info = await response.json()

    yandex_id = user_info["id"]
    login = user_info["login"]
    email = user_info.get("default_email")

    query = select(users).where(users.c.yandex_id == yandex_id)
    user = await database.fetch_one(query)

    if user:
        print(f"User already exists: {user}")
        user_id = user["id"]
    else:
        print(f"Inserting new user: {yandex_id}, {login}, {email}")
        query = users.insert().values(yandex_id=yandex_id, login=login, email=email)
        try:
            user_id = await database.execute(query)
        except IntegrityError as e:
            print(f"IntegrityError while inserting user: {e}")
            query = select(users).where(users.c.yandex_id == yandex_id)
            user = await database.fetch_one(query)
            if not user:
                return HTMLResponse("User not found after IntegrityError", status_code=500)
            user_id = user["id"]

    session_token = os.urandom(24).hex()
    print(f"Creating session for user_id: {user_id} with token: {session_token}")

    query = sessions.insert().values(user_id=user_id, token=session_token)
    try:
        await database.execute(query)
    except Exception as e:
        print(f"Failed to insert session: {e}")
        return HTMLResponse("Failed to create session", status_code=500)

    response = HTMLResponse(f"""
    <html>
        <body>
            <script>
                window.addEventListener('load', function() {{
                    window.location.reload();
                }});
                document.cookie = "session_token={session_token};path=/";
                window.opener.location.href = "/";
                window.close();
            </script>
        </body>
    </html>
    """)
    response.set_cookie(key="session_token", value=session_token)
    return response

async def run_subprocess(command):
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        raise Exception(f"Ошибка выполнения команды {' '.join(command)}: {stderr.decode()}")
    return stdout.decode()

@app.get("/run-parser", response_class=JSONResponse)
async def run_parser(request: Request, url: str = Query(...)):
    # Проверка корректности URL
    if not validators.url(url):
        return JSONResponse(status_code=400, content={"error": "Некорректный URL"})
    
    session_token = request.cookies.get("session_token")
    if not session_token:
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    query = select(sessions).where(sessions.c.token == session_token)
    session = await database.fetch_one(query)
    if not session:
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    user_id = session["user_id"]
    
    # Проверка, есть ли пользователь уже в очереди с данным URL
    async with lock:
        if (user_id, url) in queue or (user_id, url) == processing_user:
            position = next((i + 1 for i, (uid, uurl) in enumerate(queue) if uid == user_id and uurl == url), None)
            if position is None and (user_id, url) == processing_user:
                position = 0  # User is currently being processed
            return JSONResponse(content={"message": f"Вы уже находитесь в очереди. Ваша позиция: {position}"})

        # Добавление пользователя в очередь
        queue.append((user_id, url))
        user_status[(user_id, url)] = "В очереди"

    # Проверка положения в очереди
    position = next((i + 1 for i, (uid, uurl) in enumerate(queue) if uid == user_id and uurl == url), None)
    return JSONResponse(content={"message": f"Вы находитесь в очереди. Ваша позиция: {position}"})






async def process_queue():
    global processing_user
    while True:
        if queue and processing_user is None:
            async with lock:
                processing_user = queue.popleft()

            user_id, url = processing_user
            profile_path = f"/tmp/chrome_profile_{os.getpid()}"
            os.makedirs(profile_path, exist_ok=True)

            try:
                user_status[(user_id, url)] = "Обработка"

                # Таймер выполнения парсера
                timeout = 90  # 1 минута
                await run_subprocess_with_timeout(["python3", "parser.py", url], timeout)

                await run_subprocess(["python3", "gpt_answer.py"])

                user_directory = f"user_files/{user_id}"
                os.makedirs(user_directory, exist_ok=True)

                timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
                output_file_path = os.path.join(user_directory, f"gpt_output_{timestamp}.json")

                async with aiofiles.open(output_file_path, "w", encoding="utf-8") as f:
                    async with aiofiles.open("gpt_output.json", "r", encoding="utf-8") as gpt_f:
                        gpt_output = await gpt_f.read()
                        await f.write(gpt_output)

                sorted_results_path = os.path.join(user_directory, "sorted_results.txt")
                shutil.move("sorted_results.txt", sorted_results_path)

                query = generation_history.insert().values(user_id=user_id, file_path=output_file_path, created_at=datetime.datetime.now())
                await database.execute(query)

                user_status[(user_id, url)] = f"Обработка завершена."
                print(f"Обработка завершена для пользователя {user_id}")

            except Exception as e:
                user_status[(user_id, url)] = f"Ошибка: {str(e)}"
                print(f"Ошибка при обработке пользователя {user_id}: {e}")

            finally:
                shutil.rmtree(profile_path, ignore_errors=True)
                processing_user = None
        else:
            await asyncio.sleep(1)


async def run_subprocess_with_timeout(command, timeout):
    proc = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        stdout, stderr = await proc.communicate()
        raise Exception(f"Превышено время ожидания. Попробуйте снова")
    return stdout.decode(), stderr.decode()

@app.on_event("startup")
async def startup():
    metadata.create_all(engine)
    await database.connect()
    asyncio.create_task(process_queue())

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()


@app.get("/history", response_class=HTMLResponse)
async def history(request: Request):
    session_token = request.cookies.get("session_token")
    if not session_token:
        return HTMLResponse(content="<script>window.location.href = '/';</script>", status_code=401)

    query = select(sessions).where(sessions.c.token == session_token)
    session = await database.fetch_one(query)
    if not session:
        return HTMLResponse(content="<script>window.location.href = '/';</script>", status_code=401)

    user_id = session["user_id"]
    query = select(generation_history).where(generation_history.c.user_id == user_id).order_by(generation_history.c.created_at.desc())
    history_records = await database.fetch_all(query)

    grouped_history = {}
    for record in history_records:
        created_at_date = record['created_at'].astimezone().date()
        date_str = created_at_date.strftime('%Y-%m-%d')

        if date_str not in grouped_history:
            grouped_history[date_str] = []

        file_path = record['file_path']
        try:
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                json_content = await f.read()
            json_data = json.loads(json_content)
            title = json_data.get('Заголовок', '')
            text = json_data.get('Текст', '')

            grouped_history[date_str].append({
                'title': title,
                'text': text,
                'created_at': record['created_at'].strftime('%H:%M:%S'),
                'file_path': file_path
            })
            print(f"Loaded JSON data for record: {record['created_at']}")
        except FileNotFoundError:
            print(f"File not found: {file_path}")
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON file {file_path}: {str(e)}")
    print(f"Grouped history: {grouped_history}")
    print("Grouped history:")
    for date, records in grouped_history.items():
        print(f"Date: {date}")
        for record in records:
            print(f"  Title: {record['title']}")
            print(f"  Text: {record['text']}")
            print(f"  Created At: {record['created_at']}")
            print(f"  File Path: {record['file_path']}")
    return templates.TemplateResponse("history.html", {"request": request, "grouped_history": grouped_history})


   
    


@app.get("/check-queue", response_class=JSONResponse)
async def check_queue(request: Request, url: str):
    session_token = request.cookies.get("session_token")
    if not session_token:
        raise HTTPException(status_code=401, detail="Unauthorized")

    query = select(sessions).where(sessions.c.token == session_token)
    session = await database.fetch_one(query)
    if not session:
        raise HTTPException(status_code=401, detail="Unauthorized")

    user_id = session["user_id"]

    async with lock:
        position = -1
        if (user_id, url) in queue:
            position = queue.index((user_id, url)) + 1
        status = user_status.get((user_id, url), "В очереди")
        if status.startswith("Обработка завершена") or "Ошибка" in status:
            user_status.pop((user_id, url), None)

    return JSONResponse(content={"message": status, "position": position})

@app.get("/analyze-data", response_class=HTMLResponse)
async def analyze_data_page(request: Request):
    return templates.TemplateResponse("analyze-data.html", {"request": request})


@app.post("/upload_and_predict", response_class=HTMLResponse)
async def upload_and_predict(request: Request, file: UploadFile = File(None)):
    if file is None:
        return templates.TemplateResponse("analyze-data.html", {
            "request": request,
            "result_message": "Ошибка: файл не был загружен."
        })

    file_location = f"temp_{file.filename}"
    try:
        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        session_token = request.cookies.get("session_token")
        if not session_token:
            raise HTTPException(status_code=401, detail="Unauthorized")

        query = select(sessions).where(sessions.c.token == session_token)
        session = await database.fetch_one(query)
        if not session:
            raise HTTPException(status_code=401, detail="Unauthorized")

        user_id = session["user_id"]
        user_directory = f"user_files/{user_id}"
        os.makedirs(user_directory, exist_ok=True)
        
        await run_subprocess(['python', 'analyze_csv/main2.py', file_location])

        result_file_path = os.path.join(user_directory, 'analysis_result.json')
        
        if os.path.exists('output/analysis_result.json'):
            shutil.move('output/analysis_result.json', result_file_path)

            with open(result_file_path, 'r', encoding='utf-8') as f:
                selling_ads_num = json.load(f)
            
            # Сохранение результатов в CSV файл
            csv_file_path = os.path.join(user_directory, 'analysis_result.csv')
            with open(csv_file_path, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['Заголовок', 'Текст', 'Показы', 'CTR (%)', 'Ср. цена клика (руб.)', 'Отказы (%)', 'Конверсия (%)']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                for ad in selling_ads_num:
                    # Исключаем поле 'is_selling' из записи
                    ad_filtered = {key: value for key, value in ad.items() if key in fieldnames}
                    writer.writerow(ad_filtered)

            return templates.TemplateResponse("analyze-data.html", {
                "request": request,
                "result_message": f"Результаты сохранены в CSV файле",
                "selling_ads": selling_ads_num,
                "csv_file_path": csv_file_path  # Передача пути к CSV файлу в шаблон
            })
        else:
            return templates.TemplateResponse("analyze-data.html", {
                "request": request,
                "result_message": "Не удалось создать результат анализа. Ошибка в анализе данных, проверьте что файл имеет формат CSV, колонки Заголовок, Текст, Показы, CTR (%), Ср. цена клика (руб.), Отказы (%), Конверсия (%)"
            })
    except Exception as e:
        if "Отсутствуют необходимые колонки" in str(e):
            return templates.TemplateResponse("analyze-data.html", {
                "request": request,
                "result_message": "Ошибка в анализе данных, проверьте что файл имеет формат CSV, колонки Заголовок, Текст, Показы, CTR (%), Ср. цена клика (руб.), Отказы (%), Конверсия (%)"
            })
        return templates.TemplateResponse("analyze-data.html", {
            "request": request,
            "result_message": f"Ошибка: {str(e)}"
        })
    finally:
        if os.path.exists(file_location):
            os.remove(file_location)


@app.get("/download-analysis-result", response_class=FileResponse)
async def download_analysis_result(request: Request):
    session_token = request.cookies.get("session_token")
    if not session_token:
        raise HTTPException(status_code=401, detail="Unauthorized")

    query = select(sessions).where(sessions.c.token == session_token)
    session = await database.fetch_one(query)
    if not session:
        raise HTTPException(status_code=401, detail="Unauthorized")

    user_id = session["user_id"]
    user_directory = f"user_files/{user_id}"
    csv_file_path = os.path.join(user_directory, 'analysis_result.csv')

    if not os.path.exists(csv_file_path):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(path=csv_file_path, filename="analysis_result.csv", media_type='text/csv')
    

@app.get("/get-result", response_class=JSONResponse)
async def get_result(request: Request):
    session_token = request.cookies.get("session_token")
    if not session_token:
        raise HTTPException(status_code=401, detail="Unauthorized")

    query = select(sessions).where(sessions.c.token == session_token)
    session = await database.fetch_one(query)
    if not session:
        raise HTTPException(status_code=401, detail="Unauthorized")

    user_id = session["user_id"]
    user_directory = f"user_files/{user_id}"

    if not os.path.exists(user_directory):
        raise HTTPException(status_code=404, detail="Results not found")

    result_files = [f for f in os.listdir(user_directory) if f.endswith(".json")]
    if not result_files:
        raise HTTPException(status_code=404, detail="Results not found")

    # Сортировка файлов по дате изменения, чтобы получить последний файл
    result_files.sort(key=lambda f: os.path.getmtime(os.path.join(user_directory, f)), reverse=True)
    latest_file = result_files[0]
    latest_file_path = os.path.join(user_directory, latest_file)

    async with aiofiles.open(latest_file_path, "r", encoding="utf-8") as f:
        result_content = await f.read()
    latest_result_data = json.loads(result_content)

    return JSONResponse(content={"result_data": latest_result_data, "file_name": latest_file})


@app.get("/download-sorted-results", response_class=FileResponse)
async def download_sorted_results(request: Request):
    session_token = request.cookies.get("session_token")
    if not session_token:
        raise HTTPException(status_code=401, detail="Unauthorized")

    query = select(sessions).where(sessions.c.token == session_token)
    session = await database.fetch_one(query)
    if not session:
        raise HTTPException(status_code=401, detail="Unauthorized")

    user_id = session["user_id"]
    user_directory = f"user_files/{user_id}"
    sorted_results_path = os.path.join(user_directory, "sorted_results.txt")

    if not os.path.exists(sorted_results_path):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(path=sorted_results_path, filename="sorted_results.txt", media_type='text/plain')

@app.post("/analyze-data", response_class=JSONResponse)
async def analyze_data(request: Request):
    try:
        # Путь к вашему скрипту, выполняющему анализ данных
        script_path = "analyze_csv/main2.py"

        # Запуск скрипта анализа данных
        process = await asyncio.create_subprocess_exec(
            "python3", script_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_message = stderr.decode() if stderr else "Unknown error"
            raise HTTPException(status_code=500, detail=f"Ошибка выполнения скрипта: {error_message}")

        # Чтение результатов анализа (предположим, результаты сохраняются в файле JSON)
        result_file_path = "output/output.json"
        if not os.path.exists(result_file_path):
            raise HTTPException(status_code=404, detail="Результаты не найдены")

        with open(result_file_path, "r", encoding="utf-8") as f:
            result_data = json.load(f)

        return JSONResponse(content=result_data)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при анализе данных: {str(e)}")



@app.post("/img-generation-form", response_class=HTMLResponse)
async def img_generation_form_post(request: Request):
    url = 'https://processed-model-result.s3.us-east-2.amazonaws.com/a6d21138-ec38-4d7a-8bd0-8fcfbf304f61_0.png'
    await run_subprocess(['python', 'image_generation/image_generation.py', url])
    

@app.get("/img-generation-form", response_class=HTMLResponse)
async def img_generation_form(request: Request):
    logging.info(f"HTTP GET request to /img-generation-form: {request.client.host}")
    session_token = request.cookies.get("session_token")
    if not session_token:
        return HTMLResponse(content="<script>window.location.href = '/';</script>", status_code=401)
    query = select(sessions).where(sessions.c.token == session_token)
    session = await database.fetch_one(query)
    if not session:
        return HTMLResponse(content="<script>window.location.href = '/';</script>", status_code=401)

    # user_id = session["user_id"]
    return templates.TemplateResponse("img-generation-form.html", {"request": request, "session": session})




@app.on_event("startup")
async def startup():
    metadata.create_all(engine)
    await database.connect()
    asyncio.create_task(process_queue())

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
