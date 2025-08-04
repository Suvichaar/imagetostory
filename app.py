import streamlit as st
from PIL import Image
import requests
import json
import base64
import boto3
import time
from io import BytesIO
from datetime import datetime

# ========================
# 🔐 Load Secrets
# ========================
AZURE_ENDPOINT     = st.secrets["azure_api"]["AZURE_OPENAI_ENDPOINT"]
AZURE_API_KEY      = st.secrets["azure_api"]["AZURE_OPENAI_API_KEY"]

DALE_API_KEY       = st.secrets["azure"]["AZURE_API_KEY"]
TTS_URL            = st.secrets["azure"]["AZURE_TTS_URL"]

AWS_ACCESS_KEY     = st.secrets["aws"]["AWS_ACCESS_KEY"]
AWS_SECRET_KEY     = st.secrets["aws"]["AWS_SECRET_KEY"]
AWS_REGION         = st.secrets["aws"]["AWS_REGION"]
AWS_BUCKET         = st.secrets["aws"]["AWS_BUCKET"]
S3_PREFIX          = st.secrets["aws"]["S3_PREFIX"]
CDN_BASE           = st.secrets["aws"]["CDN_BASE"]
DEFAULT_ERROR_IMAGE = "https://media.suvichaar.org/default-error.jpg"

# ========================
# 🚀 GPT-4 Vision Call
# ========================
def call_gpt4_vision(base64_img):
    endpoint = f"{AZURE_ENDPOINT}/openai/deployments/gpt-4/chat/completions?api-version=2024-08-01-preview"
    headers = {"Content-Type": "application/json", "api-key": AZURE_API_KEY}
    system_prompt = """
You are a teaching assistant. The student has uploaded a notes image.

Your job:
1. Extract a short and catchy title → storytitle
2. Summarise the content and break it into 5 slides (s2paragraph1 to s6paragraph1), each under 400 characters.
3. For each paragraph (including the title), generate a vivid DALL·E prompt (vector-style, no text). → s1alt1 to s6alt1

Respond in this JSON format:
{
  "storytitle": "...",
  "s2paragraph1": "...",
  "s3paragraph1": "...",
  "s4paragraph1": "...",
  "s5paragraph1": "...",
  "s6paragraph1": "...",
  "s1alt1": "...",
  "s2alt1": "...",
  "s3alt1": "...",
  "s4alt1": "...",
  "s5alt1": "...",
  "s6alt1": "..."
}
"""
    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}}]}
        ],
        "temperature": 0.7,
        "max_tokens": 1000
    }
    res = requests.post(endpoint, headers=headers, json=payload)
    return json.loads(res.json()["choices"][0]["message"]["content"])

# ========================
# 🎨 Generate and Upload DALL·E Images
# ========================
def generate_and_upload_images(result):
    s3 = boto3.client("s3", aws_access_key_id=AWS_ACCESS_KEY,
                           aws_secret_access_key=AWS_SECRET_KEY,
                           region_name=AWS_REGION)
    slug = result["storytitle"].lower().replace(" ", "-").replace(":", "")
    final_json = result.copy()

    for i in range(1, 7):
        prompt = result.get(f"s{i}alt1", "")
        url = "https://njnam-m3jxkka3-swedencentral.cognitiveservices.azure.com/openai/deployments/dall-e-3/images/generations?api-version=2024-02-01"
        headers = {"Content-Type": "application/json", "api-key": DALE_API_KEY}
        payload = {"prompt": prompt, "n": 1, "size": "1024x1024"}

        for _ in range(3):
            res = requests.post(url, headers=headers, json=payload)
            if res.status_code == 200:
                image_url = res.json()["data"][0]["url"]
                img = Image.open(BytesIO(requests.get(image_url).content)).convert("RGB").resize((720, 1200))
                buffer = BytesIO()
                img.save(buffer, format="JPEG")
                buffer.seek(0)
                key = f"{S3_PREFIX}{slug}/slide{i}.jpg"
                s3.upload_fileobj(buffer, AWS_BUCKET, key)
                final_json[f"s{i}image1"] = f"{CDN_BASE}{key}"
                break
            time.sleep(5)
        else:
            final_json[f"s{i}image1"] = DEFAULT_ERROR_IMAGE

    # Portrait Cover
    try:
        portrait = Image.open(BytesIO(requests.get(final_json["s1image1"]).content)).convert("RGB").resize((640, 853))
        buffer = BytesIO()
        portrait.save(buffer, format="JPEG")
        buffer.seek(0)
        portrait_key = f"{S3_PREFIX}{slug}/portrait_cover.jpg"
        s3.upload_fileobj(buffer, AWS_BUCKET, portrait_key)
        final_json["potraitcoverurl"] = f"{CDN_BASE}{portrait_key}"
    except:
        final_json["potraitcoverurl"] = DEFAULT_ERROR_IMAGE

    return final_json

# ========================
# ✍️ SEO Metadata
# ========================
def generate_seo(result):
    endpoint = f"{AZURE_ENDPOINT}/openai/deployments/gpt-4/chat/completions?api-version=2024-08-01-preview"
    headers = {"Content-Type": "application/json", "api-key": AZURE_API_KEY}
    prompt = f"""
Generate SEO metadata for this web story:

Title: {result['storytitle']}
Slides:
- {result['s2paragraph1']}
- {result['s3paragraph1']}
- {result['s4paragraph1']}
- {result['s5paragraph1']}
- {result['s6paragraph1']}

Respond as:
{{ "metadescription": "...", "metakeywords": "..." }}
"""
    payload = {
        "messages": [
            {"role": "system", "content": "You are an expert SEO assistant."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.5,
        "max_tokens": 300
    }
    res = requests.post(endpoint, headers=headers, json=payload)
    return json.loads(res.json()["choices"][0]["message"]["content"])

# ========================
# 💻 Streamlit App (Tab 1)
# ========================
st.set_page_config(page_title="Suvichaar Story Generator", layout="wide")
tabs = st.tabs(["🧠 Generate JSON from Notes Image", "📄 Placeholder for Tab 2", "📄 Placeholder for Tab 3"])

with tabs[0]:
    st.header("🧠 Generate JSON from Notes Image")
    uploaded_image = st.file_uploader("Upload a notes image (JPG/PNG)", type=["jpg", "jpeg", "png"])

    if uploaded_image is not None:
        st.image(uploaded_image, caption="Uploaded Notes", use_column_width=True)
        base64_img = base64.b64encode(uploaded_image.read()).decode("utf-8")

        with st.spinner("⏳ Generating content using GPT-4 Vision..."):
            result = call_gpt4_vision(base64_img)

        with st.spinner("🎨 Generating images and uploading to S3..."):
            final_json = generate_and_upload_images(result)

        with st.spinner("✍️ Generating SEO metadata..."):
            seo_data = generate_seo(final_json)
            final_json.update(seo_data)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_filename = f"{result['storytitle'].replace(' ', '_').lower()}_{timestamp}.json"
        json_str = json.dumps(final_json, indent=2)

        st.success("✅ JSON generated successfully!")
        st.download_button("📥 Download JSON", data=json_str, file_name=json_filename, mime="application/json")
