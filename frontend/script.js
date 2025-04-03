document.addEventListener('DOMContentLoaded', () => {
    // --- Configuration ---
    // !!! IMPORTANT: Replace this with the ACTUAL URL of your DEPLOYED backend !!!
    const API_ENDPOINT = 'https://ewaste-estimator-app.onrender.com';
    // --- Get DOM Elements ---
    const uploadForm = document.getElementById('upload-form');
    const imageUpload = document.getElementById('image-upload');
    const imagePreviewContainer = document.getElementById('image-preview-container');
    const imagePreview = document.getElementById('image-preview');
    const fileNameDisplay = document.getElementById('file-name-display');
    const brandInput = document.getElementById('brand');
    const modelInput = document.getElementById('model');
    const issuesInput = document.getElementById('issues');
    const submitButton = document.getElementById('submit-button');
    const buttonText = submitButton.querySelector('.button-text');
    const spinner = submitButton.querySelector('.spinner');
    const statusMessage = document.getElementById('status-message');
    const resultsDisplay = document.getElementById('results-display');
    const priceRangeDisplay = document.getElementById('price-range');
    const detectedInfoDisplay = document.getElementById('detected-info');

    // --- Event Listeners ---

    // Handle file selection and preview
    imageUpload.addEventListener('change', (event) => {
        const file = event.target.files[0];
        if (file) {
            // Show filename
            fileNameDisplay.textContent = file.name.length > 30 ? `${file.name.substring(0, 27)}...` : file.name;

            // Show preview
            const reader = new FileReader();
            reader.onload = (e) => {
                imagePreview.src = e.target.result;
                imagePreviewContainer.classList.remove('hidden');
            }
            reader.readAsDataURL(file);

            // Clear previous results and status on new file selection
            clearStatus();
            resultsDisplay.classList.add('hidden');
        } else {
            // No file chosen or selection cancelled
            fileNameDisplay.textContent = 'No file chosen';
            imagePreviewContainer.classList.add('hidden');
            imagePreview.src = '#'; // Clear preview src
        }
    });

// Handle form submission
uploadForm.addEventListener('submit', async (event) => {
    event.preventDefault(); // Stop default form submission

    // Get input values
    const brand = brandInput.value.trim();
    const model = modelInput.value.trim();
    const issues = issuesInput.value.trim();

    // Validate input fields
    if (!brand || !model) {
        showStatus("⚠️ Please enter both brand and model.", "error");
        return;
    }

    const file = imageUpload.files[0];
    if (!file) {
        showStatus("⚠️ Please select an image file first.", "error");
        return;
    }

    // --- Prepare UI for loading ---
    setLoadingState(true);
    clearStatus(); // Clear previous errors/status
    resultsDisplay.classList.add('hidden'); // Hide old results

    // --- Debugging Log ---
    console.log(`DEBUG: Sending request -> Brand: ${brand}, Model: ${model}, Issues: ${issues}`);

    // --- API Call ---
    try {
        const response = await fetch(`${API_ENDPOINT}/estimate?brand=${encodeURIComponent(brand)}&model=${encodeURIComponent(model)}&issues=${encodeURIComponent(issues)}`, {
            method: "GET",
        });

        if (!response.ok) {
            throw new Error(`Server error: ${response.status} - ${response.statusText}`);
        }

        const result = await response.json();
        console.log("DEBUG: Response received", result);

        if (!result.estimated_price) {
            showStatus("⚠️ No valid estimate found.", "error");
            return;
        }

        displayResults(result);
    } catch (error) {
        console.error("Network Error:", error);
        showStatus("❌ Could not connect to the estimation server. Try again later.", "error");
    } finally {
        // --- Reset UI after loading ---
        setLoadingState(false);
    }
});


            // Check if response is okay (status code 200-299)
            if (response.ok) {
                const result = await response.json(); // Parse JSON response from backend
                displayResults(result);
            } else {
                // Handle errors from the backend (e.g., 400, 500)
                let errorMsg = `Error: ${response.status} - ${response.statusText}`;
                try {
                    // Try to get more specific error message from backend response body
                    const errorResult = await response.json();
                    if (errorResult && errorResult.error) {
                        errorMsg = `Error: ${errorResult.error}`;
                    }
                } catch (e) {
                    // If response body isn't JSON or other issue, use the status text
                    console.warn("Could not parse error response body:", e);
                }
                 showStatus(errorMsg, 'error');
                resultsDisplay.classList.add('hidden'); // Ensure results are hidden on error
            }
        } catch (error) {
            // Handle network errors (fetch failed to connect)
            console.error('Network Error:', error);
            showStatus('Network Error: Could not connect to the estimation server. Please try again later.', 'error');
            resultsDisplay.classList.add('hidden'); // Ensure results are hidden on error
        } finally {
            // --- Reset UI after loading ---
            setLoadingState(false);
        }
    });

    // --- Helper Functions ---

    function setLoadingState(isLoading) {
        submitButton.disabled = isLoading;
        if (isLoading) {
            buttonText.textContent = 'Processing...'; // Optional: change text
            spinner.classList.remove('hidden');
        } else {
            buttonText.textContent = 'Get Estimate';
            spinner.classList.add('hidden');
        }
    }

    function showStatus(message, type = 'info') { // type can be 'info', 'error', 'loading'
        statusMessage.textContent = message;
        statusMessage.className = 'status'; // Reset classes
        if (type === 'error') {
            statusMessage.classList.add('error');
        } else if (type === 'loading') {
             statusMessage.classList.add('loading');
        }
         // 'info' type doesn't need an extra class unless styled specifically
    }

    function clearStatus() {
        statusMessage.textContent = '';
        statusMessage.className = 'status'; // Reset classes
    }

    function displayResults(result) {
        // Update the frontend elements with data from the backend response
        priceRangeDisplay.textContent = result.estimated_price || 'N/A';
        detectedInfoDisplay.textContent = result.detected_info || 'Analysis details not available.';

        // Show the results section
        resultsDisplay.classList.remove('hidden');
    }

}); // End DOMContentLoaded
