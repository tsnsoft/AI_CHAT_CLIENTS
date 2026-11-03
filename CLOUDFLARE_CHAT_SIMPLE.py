# -*- coding: utf-8 -*-
"""
Простой консольный чат с нейросетью (Cloudflare Workers AI).

КАК ПОЛУЧИТЬ БЕСПЛАТНЫЙ ДОСТУП:
1. Зарегистрируйтесь на сайте: https://dash.cloudflare.com/sign-up
2. В меню слева откройте: AI -> Workers AI -> Use REST API
3. Скопируйте свой Account ID и создайте API Token (шаблон Workers AI).
4. Вставьте полученные значения в кавычки ниже.
"""

import requests  # Библиотека для отправки запросов в интернет (pip install requests)

# ======================================================================
# 1. НАСТРОЙКИ (вставьте сюда свои данные)
# ======================================================================

ACCOUNT_ID = "ВСТАВЬТЕ_СВОЙ_ACCOUNT_ID"
API_TOKEN = "ВСТАВЬТЕ_СВОЙ_ТОКЕН"

# Название бесплатной модели нейросети
MODEL = "@cf/meta/llama-4-scout-17b-16e-instruct"

# Начальная инструкция, которая задаёт характер и роль ИИ
SYSTEM_PROMPT = "Ты дружелюбный помощник. Отвечай на языке пользователя."

# Максимальная длина ответа (1 токен — это примерно 3-4 буквы)
MAX_TOKENS = 1500

# Полный адрес сервера Cloudflare
API_URL = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/run/{MODEL}"

# Заголовок с токеном (так сервер узнаёт ваш аккаунт)
HEADERS = {"Authorization": f"Bearer {API_TOKEN}"}


# ======================================================================
# 2. ФУНКЦИЯ ОТПРАВКИ ЗАПРОСА
# ======================================================================

def ask_model(messages):
    """
    Отправляет список сообщений (messages) на сервер.
    Возвращает текст ответа ИИ (или пустую строку "", если произошла ошибка).
    """
    payload = {
        "messages": messages,
        "max_tokens": MAX_TOKENS,
    }

    try:
        # Отправляем запрос на сервер (ждём ответ максимум 120 секунд)
        response = requests.post(API_URL, headers=HEADERS, json=payload, timeout=120)
        # Переводим ответ сервера из формата JSON в обычный словарь Python
        data = response.json()
    except Exception as e:
        print(f"Ошибка сети: {e}")
        return ""

    # Проверяем, успешно ли сервер обработал запрос
    if data.get("success") == False:
        print(f"Ошибка сервера: {data.get('errors')}")
        return ""

    # Достаём текст ответа из словаря result
    result = data["result"]
    if "response" in result:
        return result["response"]
    else:
        return result["choices"][0]["message"]["content"]


# ======================================================================
# 3. ОСНОВНАЯ ПРОГРАММА (ЦИКЛ ЧАТА)
# ======================================================================

def main():
    # Проверяем, вписал ли студент свои данные вместо заглушек
    if "ВСТАВЬТЕ" in ACCOUNT_ID or "ВСТАВЬТЕ" in API_TOKEN:
        print("Ошибка: сначала впишите свои ACCOUNT_ID и API_TOKEN в начале файла!")
        return

    # Список истории диалога. Сервер сам ничего не помнит между запросами,
    # поэтому мы храним всю переписку здесь и каждый раз отправляем её целиком.
    history = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]

    print(f"Чат запущен! Модель: {MODEL}")
    print("Команды: 'сброс' — очистить память, 'выход' — закрыть программу.\n")

    while True:
        user_text = input("Вы: ").strip()

        # Если пользователь просто нажал Enter без текста — пропускаем
        if user_text == "":
            continue

        # Команда выхода из программы
        if user_text.lower() == "выход":
            print("До свидания!")
            break

        # Команда очистки истории диалога
        if user_text.lower() == "сброс":
            history = [
                {"role": "system", "content": SYSTEM_PROMPT}
            ]
            print("История диалога очищена.\n")
            continue

        # 1. Добавляем вопрос пользователя в список истории
        user_message = {"role": "user", "content": user_text}
        history.append(user_message)

        # 2. Отправляем всю историю нейросети и получаем ответ
        answer = ask_model(history)

        # 3. Если произошла ошибка (вернулась пустая строка) — удаляем вопрос из истории
        if answer == "":
            history.pop()
            continue

        # 4. Сохраняем ответ ИИ в историю и выводим его на экран
        ai_message = {"role": "assistant", "content": answer}
        history.append(ai_message)
        print(f"\nИИ: {answer}\n")


if __name__ == "__main__":
    main()
