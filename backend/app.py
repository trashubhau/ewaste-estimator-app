from flask import Flask, request, jsonify
import google.generativeai as genai
from PIL import Image
import io
import json

app = Flask(__name__)

# Configure Gemini API Key
GOOGLE_API_KEY = "your_gemini_api_key_here"
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')  # Ensure the model supports image input

# Price structure (Example)
PRICE_STRUCTURE = {
    "smartphone": {"fair": [10, 50], "good": [51, 150], "great": [151, 400]},
    "laptop": {"fair": [30, 100], "good": [101, 350], "great": [351, 800]},
    "tablet": {"fair": [20, 70], "good": [71, 200], "great": [201, 500]},
    "monitor": {"fair": [5, 25], "good": [26, 75], "great": [76, 150]},
    "keyboard": {"fair": [1, 5], "good": [6, 15], "great": [16, 40]},
    "mouse": {"fair": [1, 5], "good": [6, 15], "great": [16, 35]},
    "unknown": {"fair": [1, 10], "good": [1, 10], "great": [1, 10]},
}

def analyze_image_with_gemini(image_data):
    """Analyzes the image with Gemini AI and returns the device type, condition, and extracted text."""
    try:
        img_pil = Image.open(io.BytesIO(image_data))
        prompt = """
        Analyze the following image of an electronic waste item.
        Provide your response as a JSON object with the following keys:
        - "device_type": (e.g., smartphone, laptop, tablet, etc.)
        - "condition_description": (visible physical condition like scratches, cracks, dents)
        - "extracted_text": (brand name or model number if visible, otherwise null)
        """

        response = model.generate_content([prompt, img_pil], stream=False)
        response.resolve()

        try:
            cleaned_text = response.text.strip().lstrip('json').rstrip('').strip()
            return json.loads(cleaned_text)
        except json.JSONDecodeError:
            return {"raw_text": response.text}

    except Exception as e:
        return {"error": str(e)}

def categorize_condition(description):
    """Categorizes the condition based on keywords in the description."""
    description_lower = description.lower() if description else ""
    fair_keywords = ["crack", "shatter", "broken", "major dent", "heavy wear", "missing", "doesn't power", "water damage"]
    good_keywords = ["minor scratch", "scuff", "small dent", "moderate wear", "fully functional"]
    great_keywords = ["like new", "pristine", "excellent", "no visible marks"]

    if any(keyword in description_lower for keyword in fair_keywords):
        return "fair"
    elif any(keyword in description_lower for keyword in great_keywords):
        return "great"
    elif any(keyword in description_lower for keyword in good_keywords):
        return "good"
    else:
        return "good"

def get_price_estimate(device_type, condition_category):
    """Retrieves the price range from the predefined structure."""
    device_type_lower = device_type.lower() if device_type else "unknown"
    category_prices = PRICE_STRUCTURE.get(device_type_lower, PRICE_STRUCTURE["unknown"])
    price_range = category_prices.get(condition_category, [1, 10])
    return f"${price_range[0]} - ${price_range[1]}"

@app.route('/estimate-price', methods=['POST'])
def estimate_price():
    """API endpoint to estimate the price of an e-waste item from an uploaded image."""
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    img_data = file.read()
    analysis_result = analyze_image_with_gemini(img_data)

    if "error" in analysis_result:
        return jsonify({"error": analysis_result["error"]}), 500

    device_type = analysis_result.get("device_type", "unknown")
    condition_description = analysis_result.get("condition_description", "")
    extracted_text = analysis_result.get("extracted_text", "N/A")

    condition_category = categorize_condition(condition_description)
    estimated_price = get_price_estimate(device_type, condition_category)

    response = {
        "device_type": device_type,
        "condition_description": condition_description,
        "condition_category": condition_category,
        "extracted_text": extracted_text,
        "estimated_price_range": estimated_price
    }

    return jsonify(response)

if __name__ == '__main__':
    app.run(debug=True)
