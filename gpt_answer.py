# gpt_answer.py
import openai
import json
from example import example_main

api_key = 'KEY'
openai.api_key = api_key

with open("announcement.txt", "r", encoding="utf-8") as f:
    user_input = f.read().strip()

user_input_2 = user_input[24:]

# Сделаем системное сообщение короче, чтобы сократить количество токенов
system_message = (
    "Ты маркетолог. Из запроса пользователя сделай объявление. "
    "Можно использовать не все слова, предложение должно быть логичным и понятным, продающим. "
    "Если информации мало, дополни шаблонными фразами, призывами к действию. Пиши по-русски, с правильной пунктуацией и орфографией. "
    "Без номеров телефона. Объявления должны быть короткими, логичными, продающими. Макс 100 символов. Формат ответа: Заголовок и Текст."
)


params = {
    "model": "ft:gpt-3.5-turbo-0613:personal:MODEL",
    "messages": [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_input}
    ],
    "temperature": 0.5,
    "max_tokens": 120,  # Уменьшенное значение max_tokens
    "top_p": 1,
    "frequency_penalty": 2,
    "presence_penalty": 1
}

try:
    response = openai.ChatCompletion.create(**params)
    gpt_output = response['choices'][0]['message']['content']

    # Разделяем вывод на "Заголовок" и "Текст"
    lines = gpt_output.split('\n')
    result = {"Заголовок": lines[0].strip(), "Текст": lines[1].strip()}

    with open("gpt_output.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=4)  # Убедимся, что ensure_ascii=False
except openai.error.InvalidRequestError as e:
    print(f"Ошибка: {e}")

def generate_phrases():

    system_message_2 = (
        "На вход подаётся объявление, которое нужно обработать в виде запросов на yandex wordstat по строкам"
        "Получившиеся запросы должны соответствовать запросам пользователей в поисковиках, когда они что-то ищут"
        "Запрос должен очень кратким из одного или двух слов МАКСИМУМ ИЗ ТРЁХ СЛОВ, ведь люди ленивые и не пишут связующие слова"
        "НЕ ИСПОЛЬЗУЙ сложные предложения"
        "НЕ ИСПОЛЬЗУЙ предлоги"
        "НЕ ИСПОЛЬЗУЙ прилагательные"
        "Название товара/услуги ОБЯЗАТЕЛЬНО в запросе"
        "Смысл в запросе ОБЯЗАТЕЛЕН"
        "Не используй слова 'получить, купить и тд', ведь люди их не пишут"
        "Напиши около 5 запросов"
        "Не используй списки и тд"
        "Не отвечай 'Хорошо,  я вас понял и так далее', потому что твой ответ уже должен будет подцепляться программой и если есть что-то лишнее, то программа сломается"
    )

    params_2 = {
        "model": "gpt-3.5-turbo-0125",
        "messages": [
            {"role": "system", "content": system_message_2},
            {"role": "user", "content": user_input_2}
        ],
        "temperature": 0.69,
        "max_tokens": 120,  # Уменьшенное значение max_tokens
        "top_p": 1,
        "frequency_penalty": 2,
        "presence_penalty": 1
    }

    try:
        response = openai.ChatCompletion.create(**params_2)
        gpt_output = response['choices'][0]['message']['content']

        result = [line.strip() for line in gpt_output.split('\n') if line.strip()]
        return result

    except openai.error.InvalidRequestError as e:
        print(f"Ошибка: {e}")


if __name__ == "__main__":
    phrases = generate_phrases()
    if phrases:
        example_main(phrases)

