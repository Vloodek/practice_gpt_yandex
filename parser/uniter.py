import time
import json
import re
import nltk
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from nltk.tokenize import word_tokenize
import psutil
import os
import shutil
import threading

# Загрузка ресурсов для NLTK
nltk.download('punkt')
nltk.download('stopwords')
nltk.download('wordnet')

# Лемматизация текста
def lemmatize_text(text):
    lemmatizer = WordNetLemmatizer()
    words = word_tokenize(text)
    lemmatized_words = [lemmatizer.lemmatize(word) for word in words if word.isalnum() or word == ',']
    return ' '.join(lemmatized_words)

# Очистка текста, сохранение запятых
def clean_text(text):
    text = text.lower()  # Приведение к нижнему регистру
    text = re.sub(r'-', ' ', text)  # Замена дефисов на пробелы
    text = re.sub(r'\s+', ' ', text)  # Удаление лишних пробелов
    text = re.sub(r'[^a-zа-яё0-9, ]', '', text)  # Удаление знаков препинания, кроме запятых
    return text

# Удаление повторяющихся слов, сохраняя запятые
def remove_duplicates(text):
    words = text.split()
    seen = set()
    unique_words = []
    for word in words:
        if word == ',' or word not in seen:
            seen.add(word)
            unique_words.append(word)
    return ' '.join(unique_words)

# Обработка данных для каждого URL
def process_item(item):
    combined_text = ', '.join(filter(None, [item.get('title', ''), item.get('meta_description', ''), item.get('meta_keywords', ''), item.get('headings', '')]))

    # Очистка текста
    cleaned_text = clean_text(combined_text)
    
    # Лемматизация текста
    lemmatized_text = lemmatize_text(cleaned_text)
    
    # Удаление повторяющихся слов
    unique_text = remove_duplicates(lemmatized_text)

    cleaned_text = remove_contacts(unique_text)
    
    # Замена пробелов после запятых на запятые, за которыми следуют пробелы
    cleaned_text = re.sub(r'\s*,\s*', ', ', cleaned_text)
    
    return f"Сгенерируй объявление о {cleaned_text}"

def remove_contacts(text):
    # Шаблон для поиска номеров телефонов и адресов электронной почты
    pattern = r'\b(?:\+\d{1,2}\s?)?(?:\(\d{3}\)|\d{3})[-.\s]?\d{3}[-.\s]?\d{2}[-.\s]?\d{2}\b|\b\d{6}\b|\b\(\d{3}\)\s?\d{3}-\d{2}-\d{2}\b|\b\d{4}\s?\d{6}\b|\b\(\д{4}\)\с?\д{2}-\д{2}-\д{2}\б|\б\(\д{5}\)\с?\д{1}-\д{2}-\д{2}\б|\б\д{5}\с?\д{1}-\д{2}-\д{2}\б|\б\(\д{6}\)\с?\д{2}-\д{2}-\д{2}\б|\б\д{10,}\б'
    
    # Замена найденных совпадений на пустую строку
    clean_text = re.sub(pattern, '', text)

    # Удаление возможных оставшихся "Контактный телефон:" и "Email:" с любых следующих пробелов
    clean_text = re.sub(r'Контактный телефон:\s*|Email:\s*', '', clean_text)

    # Удаление лишних пробелов
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()

    return clean_text

# Основная функция
def main():
    # Считывание данных из JSON файла
    with open('parsed_data.json', 'r', encoding='utf-8') as file:
        data = json.load(file)
    
    # Обработка данных для каждого URL
    announcements = [process_item(data)]
    
    # Объединение объявлений в одну строку с разделением по строкам
    final_text = '\n'.join(announcements)
    
    # Запись результата в файл
    with open('announcement.txt', 'w', encoding='utf-8') as file:
        file.write(final_text)

    print("Объявления сгенерированы и сохранены в 'announcement.txt'.")

def remote_call():
    main()

if __name__ == "__main__":
    main()
