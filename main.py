# main.py
import os
import json
from dotenv import load_dotenv
from huggingface_hub import InferenceClient

from trustguard import TrustGuard
from trustguard.schemas import GenericResponse
from trustguard.rules import validate_pii

from memory import ChatMemory  # memory module

# =====================================
# 1️⃣ Load Environment Variables
# =====================================
load_dotenv()
HF_TOKEN = os.getenv("HF_API_KEY")
if not HF_TOKEN:
    raise ValueError("HF_API_KEY must be set in .env")
os.environ["CHROMA_HUGGINGFACE_API_KEY"] = HF_TOKEN

# =====================================
# 2️⃣ Initialize Hugging Face LLM
# =====================================
llm = InferenceClient(
    model="openai/gpt-oss-20b",
    token=HF_TOKEN
)

# =====================================
# 3️⃣ TrustGuard PII detection
# =====================================
input_guard = TrustGuard(schema_class=GenericResponse, custom_rules=[validate_pii])
output_guard = TrustGuard(schema_class=GenericResponse, custom_rules=[validate_pii])

# =====================================
# 4️⃣ Initialize Chat Memory
# =====================================
chat_memory = ChatMemory(persist_dir="./chroma_db")

# =====================================
# 5️⃣ Continuation & Exit Keywords
# =====================================
CONTINUE_KEYWORDS = [
    "cont", "continue", "more", "keep going", "again", "yes",
    "y", "please", "tell me more", "explain further"
]
EXIT_KEYWORDS = ["exit", "bye", "q", "see you", "thanks", "thank you"]
pending_continuation = False  # global variable

# =====================================
# 6️⃣ Chat function
# =====================================
def chat(user_message: str, customer_id="default", force_no_more_details=False):
    global pending_continuation  # <-- MUST be at the top

    user_message = user_message.strip()
    if not user_message:
        return "⚠️ Please enter a message."

    if pending_continuation and (user_message.lower() in CONTINUE_KEYWORDS or user_message.strip() == ""):
        user_message = "Please continue from last answer."
    pending_continuation = False

    # INPUT VALIDATION
    input_payload = json.dumps({
        "content": user_message,
        "sentiment": "neutral",
        "tone": "neutral",
        "is_helpful": True
    })
    input_result = input_guard.validate(input_payload)
    if not input_result.is_approved:
        return f"🚫 Blocked (Input - PII): {input_result.log}"

    # Store user message
    chat_memory.add_message("user", user_message, user_id=customer_id)

    # Retrieve context
    context_messages = chat_memory.query_history(user_message, user_id=customer_id, n=5)
    context_text = "\n".join([m["content"] for m in context_messages])
    MAX_CONTEXT_CHARS = 2000
    context_text = context_text[:MAX_CONTEXT_CHARS]

    # Get user name for greeting
    user_name = chat_memory.get_user_name(customer_id)
    greeting_text = f"Hello {user_name}, " if user_name else ""

    # System Prompt
    system_prompt = (
        f"You are GenCSM, a Customer Service Management assistant powered by Generative AI. "
        f"{greeting_text} Provide helpful, friendly, and accurate responses. "
        "Reference past interactions when relevant. "
        "Do NOT output internal reasoning or <think> tags. "
        "If the answer can be expanded or clarified, end your response with "
        "'Do you want more details?'"
    )

    messages = [{"role": "system", "content": system_prompt}]
    if context_text:
        messages.append({
            "role": "system",
            "content": f"Relevant conversation history:\n{context_text}"
        })
    messages.append({"role": "user", "content": user_message})

    # Generate LLM Reply
    try:
        response = llm.chat_completion(messages=messages, max_tokens=2048, temperature=0.7)
        reply = response.choices[0].message.content.strip()
    except Exception as e:
        return f"⚠️ Model Error: {str(e)}"
    if not reply:
        return "⚠️ Model returned empty output."

    # Store assistant reply
    chat_memory.add_message("assistant", reply, user_id=customer_id)

    # Only mark continuation if not forced off
    if not force_no_more_details and "do you want more details" in reply.lower():
        pending_continuation = True

    # OUTPUT VALIDATION
    output_payload = json.dumps({
        "content": reply,
        "sentiment": "neutral",
        "tone": "neutral",
        "is_helpful": True
    })
    output_result = output_guard.validate(output_payload)
    clean_reply = output_result.data["content"].replace("<think>", "").replace("</think>", "").strip()

    # Remove “Do you want more details?” if forced
    if force_no_more_details:
        clean_reply = clean_reply.replace("Do you want more details?", "").strip()

    return clean_reply

# =====================================
# 7️⃣ CLI Interface
# =====================================
if __name__ == "__main__":

    print("🤖 GenCSM – Customer Service Assistant")
    print("Memory: ChromaDB")
    print("Safety: TrustGuard PII Protection")
    print("(type 'exit' to quit)\n")

    # Ask for user ID
    customer_id = input("Please enter your User ID: ").strip()
    if not customer_id:
        customer_id = "default"

    # Check if user name exists
    user_name = chat_memory.get_user_name(customer_id)
    if not user_name:
        user_name = input("Please enter your name: ").strip()
        if not user_name:
            user_name = "Customer"
        # Store using composite key
        composite_key = f"{customer_id}|system_name"
        chat_memory.add_message(
            "system",
            user_name,
            user_id=customer_id,
            extra_metadata={"composite": composite_key}
        )

    print(f"\nWelcome {user_name}! You can start chatting with GenCSM.\n")

    # Main loop
    while True:
        prompt = f"{user_name} : " if user_name else "Customer: "
        user_input = input(prompt).strip()

        if user_input.lower() in EXIT_KEYWORDS:
            reply = chat(user_input, customer_id=customer_id, force_no_more_details=True)
            print("GenCSM:", reply)
            break

        reply = chat(user_input, customer_id=customer_id)
        print("GenCSM:", reply)

    # Persist memory automaticlly : If you set 
    # is_persistent=True when creating the client, all changes are saved automatically.
   