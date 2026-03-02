from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8045/v1",
    api_key="sk-8887828175d649e0b91b07101ab94c90"
)

response = client.chat.completions.create(
    model="gemini-2.5-flash",
    messages=[{"role": "user", "content": "Hello"}]
)
print(response.choices[0].message.content)