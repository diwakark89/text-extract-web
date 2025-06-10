// Storage keys constants
const STORAGE_KEYS = {
  LAST_USED_SELECTORS: "last_used_selectors",
  LAST_EXAM_NAME: "last_exam_name",
  LAST_PROMPT: "last_prompt",
  LAST_TEXT_TO_REMOVE: "last_text_to_remove",
  LAST_SELECTORS_TO_REMOVE: "last_selectors_to_remove",
  LAST_TAGS: "last_tags",
  API_URL: "api_url"
};

// Default API URL (can be configured in options)
const DEFAULT_API_URL = "http://localhost:8888/api/v1/manage/mcq/save/text";

// Error handling helper
function handleStorageError(error) {
  console.error("Storage operation failed:", error);
}

// No longer needed - using a comma-separated input field now

// Save selector functionality is now automatic through the extract button
// and when the popup is closed. No manual save needed.

// Automatically save CSS selector values when they change
document.getElementById("css-selectors-input").addEventListener("change", (event) => {
  try {
    const selectorsValue = event.target.value.trim();
    if (selectorsValue) {
      // Save current value to storage
      chrome.storage.sync.set(
        { [STORAGE_KEYS.LAST_USED_SELECTORS]: selectorsValue },
        () => {
          if (chrome.runtime.lastError) {
            handleStorageError(chrome.runtime.lastError);
          }
        }
      );
    }
  } catch (error) {
    console.error("Error auto-saving selectors:", error);
  }
});

// Automatically save selectors-to-remove values when they change
document.getElementById("selectors-to-remove-input").addEventListener("change", (event) => {
  try {
    const selectorsToRemoveValue = event.target.value.trim();
    // Save current value to storage
    chrome.storage.sync.set(
      { [STORAGE_KEYS.LAST_SELECTORS_TO_REMOVE]: selectorsToRemoveValue },
      () => {
        if (chrome.runtime.lastError) {
          handleStorageError(chrome.runtime.lastError);
        }
      }
    );
  } catch (error) {
    console.error("Error auto-saving selectors-to-remove:", error);
  }
});

// Automatically save text-to-remove values when they change
document.getElementById("text-to-remove-input").addEventListener("change", (event) => {
  try {
    const textToRemoveValue = event.target.value.trim();
    // Save current value to storage
    chrome.storage.sync.set(
      { [STORAGE_KEYS.LAST_TEXT_TO_REMOVE]: textToRemoveValue },
      () => {
        if (chrome.runtime.lastError) {
          handleStorageError(chrome.runtime.lastError);
        }
      }
    );
  } catch (error) {
    console.error("Error auto-saving text-to-remove:", error);
  }
});

// Event delegation for selector actions is no longer needed
// as we're automatically saving the current value

// No longer needed - using a comma-separated input field now

// No longer needed - using a comma-separated input field now

// The saved selectors functionality has been removed
// We now only save the last used selectors directly

/**
 * Handles extracting text based on selected CSS selectors
 */
document.getElementById("extract-btn").addEventListener("click", () => {
  try {
    const outputElem = document.getElementById("output");
    if (!outputElem) {
      throw new Error("Output element not found");
    }

    const cssSelectorsInput = document.getElementById("css-selectors-input");
    if (!cssSelectorsInput) {
      outputElem.innerText =
        "CSS selectors input not found. Please reload the extension.";
      return;
    }

    const cssSelectorsValue = cssSelectorsInput.value.trim();
    const selectors = cssSelectorsValue
      ? cssSelectorsValue.split(',').map(item => item.trim()).filter(item => item.length > 0)
      : [];

    if (selectors.length === 0) {
      outputElem.innerText = "Please enter at least one valid CSS selector.";
      return;
    }

    // Get exam name value
    const examNameInput = document.getElementById("exam-name-input");
    if (!examNameInput) {
      console.warn('Exam name input not found in the DOM');
    }
    const examName = examNameInput ? examNameInput.value.trim() : '';
    console.log('Exam Name:', examName);

    // Get tags value
    const tagsInput = document.getElementById("tags-input");
    if (!tagsInput) {
      console.warn('Tags input not found in the DOM');
    }
    const tagsValue = tagsInput ? tagsInput.value.trim() : '';
    const tagList = tagsValue
      ? tagsValue.split(',').map(item => item.trim()).filter(item => item.length > 0)
      : [];
    console.log('Tag List:', tagList);

    // Get prompt value
    const prompt = document.getElementById("prompt-input").value.trim();

    // Get comma-separated text-to-remove values
    const textToRemoveInput = document.getElementById("text-to-remove-input");
    const textToRemoveValue = textToRemoveInput.value.trim();
    const textToRemoveValues = textToRemoveValue
      ? textToRemoveValue.split(',').map(item => item.trim()).filter(item => item.length > 0)
      : [];

    // Get comma-separated selectors-to-remove values
    const selectorsToRemoveInput = document.getElementById("selectors-to-remove-input");
    const selectorsToRemoveValue = selectorsToRemoveInput.value.trim();
    const selectorsToRemove = selectorsToRemoveValue
      ? selectorsToRemoveValue.split(',').map(item => item.trim()).filter(item => item.length > 0)
      : [];

    // Get user extraction options
    const includeHiddenText = document.getElementById(
      "include-hidden-text"
    ).checked;

    // Save the current selectors, examName, tagList, prompt, text-to-remove values, and selectors-to-remove as last used
    chrome.storage.sync.set(
      { 
        [STORAGE_KEYS.LAST_USED_SELECTORS]: cssSelectorsValue,
        [STORAGE_KEYS.LAST_EXAM_NAME]: examName,
        [STORAGE_KEYS.LAST_TAGS]: tagsValue,
        [STORAGE_KEYS.LAST_PROMPT]: prompt,
        [STORAGE_KEYS.LAST_TEXT_TO_REMOVE]: textToRemoveValue,
        [STORAGE_KEYS.LAST_SELECTORS_TO_REMOVE]: selectorsToRemoveValue
      },
      () => {
        if (chrome.runtime.lastError) {
          handleStorageError(chrome.runtime.lastError);
          // Continue with extraction even if saving fails
        }
      }
    );

    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      const tab = tabs && tabs.length > 0 ? tabs[0] : null;

      if (!tab || !tab.id) {
        outputElem.innerText = "No active tab found. Please try again.";
        return;
      }

      // Update UI to show we're working
      outputElem.innerText = "Extracting text...";

      // Inject and execute the content script
      try {
        chrome.scripting
          .executeScript({
            target: { tabId: tab.id },
            files: ["content-script.js"],
          })
          .then(() => {
            // No longer using reveal button functionality
            extractText();

            // Function to extract text from the page
            function extractText() {
              // Send message to content script with options
              chrome.tabs.sendMessage(
                tab.id,
                {
                  action: "extractText",
                  selectors: selectors,
                  examName: examName, // Pass exam name as string
                  tagList: tagList, // Pass tag list as array
                  prompt: prompt,
                  textToRemoveValues: textToRemoveValues,
                  selectorsToRemove: selectorsToRemove, // Pass the selectors to remove as array
                  options: {
                    includeHiddenText: includeHiddenText,
                  },
                },
                (response) => {
                  if (chrome.runtime.lastError) {
                    console.error("Error:", chrome.runtime.lastError);
                    document.getElementById("output").innerText =
                      "Error connecting to page. Please refresh and try again.";
                    return;
                  }

                  if (response && response.success) {
                    try {
                      // Process successful response and update UI directly
                      const outputElem = document.getElementById("output");

                      // If the response data is a string representing JSON
                      if (typeof response.data === 'string') {
                        try {
                          // Parse the JSON string to an object
                          const jsonData = JSON.parse(response.data);

                          // Convert back to a formatted string
                          outputElem.innerText = JSON.stringify(jsonData, null, 2);
                        } catch (e) {
                          // If parsing fails, just use the original string
                          console.error('Error parsing JSON response:', e);
                          outputElem.innerText = response.data || "No content found.";
                        }
                      } else {
                        // Just use the data as is
                        outputElem.innerText = response.data || "No content found.";
                      }

                      // Show copy and send-to-api buttons if we have content
                      const copyBtn = document.getElementById("copy-btn");
                      const apiBtn = document.getElementById("send-to-api-btn");
                      if (response.data && response.data.length > 0) {
                        // Show copy button
                        if (copyBtn) {
                          copyBtn.style.display = "inline-block";
                          copyBtn.classList.add("visible");
                          copyBtn.classList.remove("hidden");
                        }

                        // Show send to API button
                        if (apiBtn) {
                          apiBtn.style.display = "inline-block";
                          apiBtn.classList.add("visible");
                          apiBtn.classList.remove("hidden");
                        }
                      }
                    } catch (e) {
                      console.error('Error processing response:', e);
                      document.getElementById("output").innerText = response.data || "No content found.";
                    }
                  } else {
                    // Handle error
                    const errorMsg =
                      response?.error || "Unknown error during extraction";
                    console.error("Extraction error:", errorMsg);
                    document.getElementById(
                      "output"
                    ).innerText = `Error during extraction: ${errorMsg}`;
                  }
                }
              );
            }
          })
          .catch((err) => {
            console.error("Error injecting content script:", err);
            document.getElementById("output").innerText =
              "Error injecting content script. Please refresh and try again.";
          });
      } catch (error) {
        console.error("Error executing script:", error);
        outputElem.innerText =
          "Error executing script. Please refresh and try again.";
      }

      // No need to set these values here as they are already set during initialization
    });
  } catch (error) {
    console.error("Error during text extraction:", error);
    document.getElementById("output").innerText =
      "Error during extraction. Please try again.";
  }
});

document.getElementById("copy-btn").addEventListener("click", () => {
  const outputText = document.getElementById("output").innerText;

  if (
    outputText &&
    outputText !== 'Click "Extract Text" to get content.' &&
    outputText !== "No content found."
  ) {
    navigator.clipboard
      .writeText(outputText)
      .then(() => {
        const copyBtn = document.getElementById("copy-btn");
        const originalText = copyBtn.innerText;
        const originalBg = copyBtn.style.background;
        copyBtn.innerText = "Copied!";
        copyBtn.style.background = "#4caf50";

        setTimeout(() => {
          copyBtn.innerText = originalText;
          copyBtn.style.background = originalBg;
        }, 2000);
      })
      .catch((err) => {
        console.error("Failed to copy text: ", err);
      });
  }
});

/**
 * Sends the extracted JSON data to the API
 * @param {string} jsonData - The JSON data to send
 */
async function sendToAPI(jsonData) {
  // Show API response container
  const apiResponseContainer = document.getElementById("api-response-container");
  const apiResponseStatus = document.getElementById("api-response-status");

  if (apiResponseContainer && apiResponseStatus) {
    apiResponseContainer.classList.remove("hidden");
    apiResponseStatus.classList.remove("success", "error");
    apiResponseStatus.classList.add("pending");
    apiResponseStatus.textContent = "Preparing API request...";
  }

  // Set a flag to determine if we should use direct fetch or background script
  let useBackgroundFallback = false;

  try {
    // Get the API URL from storage or use default
    const result = await new Promise((resolve) => {
      chrome.storage.sync.get([STORAGE_KEYS.API_URL], (result) => {
        if (chrome.runtime.lastError) {
          handleStorageError(chrome.runtime.lastError);
          resolve({ [STORAGE_KEYS.API_URL]: DEFAULT_API_URL });
        } else {
          resolve(result);
        }
      });
    });

    const apiUrl = result[STORAGE_KEYS.API_URL] || DEFAULT_API_URL;

    if (apiResponseStatus) {
      apiResponseStatus.textContent = `Sending request to: ${apiUrl}`;
    }

    // Parse the JSON data
    const jsonObj = typeof jsonData === 'string' ? JSON.parse(jsonData) : jsonData;

    // Update status in UI
    const sendBtn = document.getElementById("send-to-api-btn");
    const originalText = sendBtn.textContent;
    sendBtn.textContent = "Sending...";
    sendBtn.disabled = true;

    // Make the fetch request with error handling
    let response;
    try {
      // If using the local API endpoint, ensure we're using the right URL
      const finalUrl = apiUrl.includes('localhost') || apiUrl.includes('127.0.0.1') 
        ? apiUrl 
        : 'http://localhost:8888/api/v1/manage/mcq/save/text';

      response = await fetch(finalUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(jsonObj),
        // Add these options to ensure network request goes through
        mode: 'cors', // This might need to be 'no-cors' depending on the server
        cache: 'no-cache',
        credentials: 'include', // Include credentials for local API
        redirect: 'follow'
      });
    } catch (networkError) {
      console.error('Network error in fetch:', networkError);
      throw new Error(`Failed to fetch: ${networkError.message}`);
    }

    // Check if we have a valid response object
    if (!response) {
      throw new Error("No response received from server");
    }

    // Get response text first to avoid parsing errors
    const responseText = await response.text();

    // Try to parse as JSON
    let responseData;
    try {
      responseData = JSON.parse(responseText);
    } catch (e) {
      responseData = { text: responseText };
    }

    // Display response in API response label
    if (apiResponseStatus) {
      if (response.ok) {
        apiResponseStatus.classList.remove("pending", "error");
        apiResponseStatus.classList.add("success");
        apiResponseStatus.textContent = `Success (${response.status}): ${JSON.stringify(responseData, null, 2).substring(0, 150)}${JSON.stringify(responseData, null, 2).length > 150 ? '...' : ''}`;
      } else {
        apiResponseStatus.classList.remove("pending", "success");
        apiResponseStatus.classList.add("error");
        apiResponseStatus.textContent = `Error (${response.status}): ${responseText.substring(0, 150)}${responseText.length > 150 ? '...' : ''}`;
      }
    }

    // Check if response is okay
    if (!response.ok) {
      throw new Error(`API request failed with status ${response.status}`);
    }

    // Show success feedback
    sendBtn.textContent = "Sent!";
    sendBtn.style.background = "#4caf50";

    // Reset button after delay
    setTimeout(() => {
      sendBtn.textContent = originalText;
      sendBtn.style.background = "";
      sendBtn.disabled = false;
    }, 2000);

    return responseData;
  } catch (error) {
    console.error('Error sending data to API:', error);

    // If it's a network error, try using the background script instead
    if (error.message.includes('Failed to fetch') && !useBackgroundFallback) {
      useBackgroundFallback = true;

      if (apiResponseStatus) {
        apiResponseStatus.textContent = "Using background fallback for API request...";
      }

      try {
        // Try using the background script to make the request
        const bgResponse = await new Promise((resolve, reject) => {
          // Store apiUrl in a local variable to ensure it's defined
          const apiUrlForBg = result[STORAGE_KEYS.API_URL] || DEFAULT_API_URL;
          // If using the local API endpoint, ensure we're using the right URL
          const finalUrl = apiUrlForBg.includes('localhost') || apiUrlForBg.includes('127.0.0.1')
            ? apiUrlForBg 
            : 'http://localhost:8888/api/v1/manage/mcq/save/text';

          chrome.runtime.sendMessage({
            action: "apiCall",
            url: finalUrl,
            method: "POST",
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(jsonObj)
          }, response => {
            if (chrome.runtime.lastError) {
              reject(new Error(chrome.runtime.lastError.message));
            } else if (!response || !response.success) {
              reject(new Error(response?.error || "Unknown error in background request"));
            } else {
              resolve(response.data);
            }
          });
        });

        // If we got here, the background request succeeded
        if (apiResponseStatus) {
          if (bgResponse.ok) {
            apiResponseStatus.classList.remove("pending", "error");
            apiResponseStatus.classList.add("success");
            apiResponseStatus.textContent = `Success via background (${bgResponse.status}): ${bgResponse.text.substring(0, 150)}${bgResponse.text.length > 150 ? '...' : ''}`;
          } else {
            apiResponseStatus.classList.remove("pending", "success");
            apiResponseStatus.classList.add("error");
            apiResponseStatus.textContent = `Error via background (${bgResponse.status}): ${bgResponse.text.substring(0, 150)}${bgResponse.text.length > 150 ? '...' : ''}`;
          }
        }

        // Show success feedback for the button
        const sendBtn = document.getElementById("send-to-api-btn");
        if (sendBtn) {
          sendBtn.textContent = bgResponse.ok ? "Sent!" : "Partial Success";
          sendBtn.style.background = bgResponse.ok ? "#4caf50" : "#ff9800";

          // Reset button after delay
          setTimeout(() => {
            sendBtn.textContent = "Send to API";
            sendBtn.style.background = "";
            sendBtn.disabled = false;
          }, 2000);
        }

        return bgResponse;
      } catch (bgError) {
        console.error('Background API call failed:', bgError);
        throw bgError; // Let the original error handler deal with this
      }
    }

    // Update API response label with error
    if (apiResponseStatus) {
      apiResponseStatus.classList.remove("pending", "success");
      apiResponseStatus.classList.add("error");
      apiResponseStatus.textContent = `Error: ${error.message}`;
    }

    // Show error feedback
    const sendBtn = document.getElementById("send-to-api-btn");
    if (sendBtn) {
      sendBtn.textContent = "Failed";
      sendBtn.style.background = "#f44336";

      // Reset button after delay
      setTimeout(() => {
        sendBtn.textContent = "Send to API";
        sendBtn.style.background = "";
        sendBtn.disabled = false;
      }, 2000);
    } else {
      console.error('Send to API button not found in the DOM');
    }

    throw error;
  }
}

// Define the message handler function separately for better cleanup
function handleExtractedTextMessage(message, sender, sendResponse) {
  if (message.type === "EXTRACTED_TEXT") {
    const outputElem = document.getElementById("output");
    const copyBtn = document.getElementById("copy-btn");

    outputElem.innerText = message.payload || "No content found.";

    // Show or hide the copy and send-to-api buttons based on whether there is content
    const apiButton = document.getElementById("send-to-api-btn");
    if (message.payload && message.payload.length > 0) {
      copyBtn.classList.add("visible");
      copyBtn.classList.remove("hidden");
      if (apiButton) {
        apiButton.classList.add("visible");
        apiButton.classList.remove("hidden");
      }
    } else {
      copyBtn.classList.add("hidden");
      copyBtn.classList.remove("visible");
      if (apiButton) {
        apiButton.classList.add("hidden");
        apiButton.classList.remove("visible");
      }
    }

    // Send acknowledgment response
    sendResponse({ status: "success" });
  }
  return true; // Keep the message channel open for asynchronous response
}

// Add the listener when the popup is opened
chrome.runtime.onMessage.addListener(handleExtractedTextMessage);

// Remove the listener when the popup is closed to prevent memory leaks
window.addEventListener("unload", () => {
  try {
    chrome.runtime.onMessage.removeListener(handleExtractedTextMessage);
  } catch (error) {
    console.error("Error removing message listener:", error);
  }
});

// Handle potential errors with the chrome API
chrome.runtime.lastError &&
  console.error("Chrome runtime error:", chrome.runtime.lastError);

/**
 * Loads a specific value from storage and sets it to an input field
 * @param {string} storageKey - The key to retrieve from storage
 * @param {string} inputId - The ID of the input element to set the value to
 */
function loadStoredValueToInput(storageKey, inputId) {
  chrome.storage.sync.get([storageKey], (result) => {
    if (chrome.runtime.lastError) {
      console.error(`Error loading ${storageKey}:`, chrome.runtime.lastError);
      return;
    }

    const inputElement = document.getElementById(inputId);
    if (!inputElement) {
      console.warn(`Input element with id ${inputId} not found`);
      return;
    }

    const storedValue = result[storageKey];

    if (storedValue !== undefined && storedValue !== null) {
      if (Array.isArray(storedValue)) {
        inputElement.value = storedValue.join(', ');
      } else {
        inputElement.value = storedValue;
      }
    }
  });
}

/**
 * Initializes the UI when popup opens
 */
document.addEventListener("DOMContentLoaded", () => {
  try {
    // No need to initialize selectors container anymore since we use a single input field

    // No need to initialize text-to-remove container anymore since we use a single input field

      // Load stored values (selectors, examName, tags, prompt, text-to-remove, selectors-to-remove)
    chrome.storage.sync.get([
      STORAGE_KEYS.LAST_USED_SELECTORS,
      STORAGE_KEYS.LAST_EXAM_NAME,
      STORAGE_KEYS.LAST_TAGS,
      STORAGE_KEYS.LAST_PROMPT,
      STORAGE_KEYS.LAST_TEXT_TO_REMOVE,
      STORAGE_KEYS.LAST_SELECTORS_TO_REMOVE
    ], (result) => {
      if (chrome.runtime.lastError) {
        handleStorageError(chrome.runtime.lastError);
        // Fall back to default selector value (now handled in HTML)
        return;
      }

      // Set exam name input value if available
      const examNameInput = document.getElementById("exam-name-input");
      if (examNameInput) {
        if (result[STORAGE_KEYS.LAST_EXAM_NAME] !== undefined && result[STORAGE_KEYS.LAST_EXAM_NAME] !== null) {
          examNameInput.value = result[STORAGE_KEYS.LAST_EXAM_NAME];
        }
      } else {
        console.warn('Exam name input element not found');
      }

      // Set tags input value if available
      const tagsInput = document.getElementById("tags-input");
      if (tagsInput) {
        if (result[STORAGE_KEYS.LAST_TAGS] !== undefined && result[STORAGE_KEYS.LAST_TAGS] !== null) {
          tagsInput.value = result[STORAGE_KEYS.LAST_TAGS];
        }
      } else {
        console.warn('Tags input element not found');
      }

      // Set prompt input value if available
      const promptInput = document.getElementById("prompt-input");
      if (promptInput) {
        if (result[STORAGE_KEYS.LAST_PROMPT] !== undefined) {
          promptInput.value = result[STORAGE_KEYS.LAST_PROMPT];
        }
      } else {
        console.warn('Prompt input element not found');
      }

      // Set text-to-remove input value if available
      const textToRemoveInput = document.getElementById("text-to-remove-input");
      if (textToRemoveInput) {
        if (result[STORAGE_KEYS.LAST_TEXT_TO_REMOVE] !== undefined) {
          textToRemoveInput.value = result[STORAGE_KEYS.LAST_TEXT_TO_REMOVE];
        }
      } else {
        console.warn('Text-to-remove input element not found');
      }

      // Set selectors-to-remove input value if available
      const selectorsToRemoveInput = document.getElementById("selectors-to-remove-input");
      if (selectorsToRemoveInput) {
        if (result[STORAGE_KEYS.LAST_SELECTORS_TO_REMOVE] !== undefined) {
          // If it's an array (from previous version), join with commas
          if (Array.isArray(result[STORAGE_KEYS.LAST_SELECTORS_TO_REMOVE])) {
            selectorsToRemoveInput.value = result[STORAGE_KEYS.LAST_SELECTORS_TO_REMOVE].join(', ');
          } else {
            // Otherwise use the string directly
            selectorsToRemoveInput.value = result[STORAGE_KEYS.LAST_SELECTORS_TO_REMOVE];
          }
        }
      } else {
        console.warn('Selectors-to-remove input element not found');
      }

      // Set CSS selectors input value if available
      const cssSelectorsInput = document.getElementById("css-selectors-input");
      if (cssSelectorsInput) {
        const lastUsedSelectors = result[STORAGE_KEYS.LAST_USED_SELECTORS];

        if (lastUsedSelectors) {
          // If it's an array (from previous version), join with commas
          if (Array.isArray(lastUsedSelectors)) {
            cssSelectorsInput.value = lastUsedSelectors.join(', ');
          } else {
            // Otherwise use the string directly
            cssSelectorsInput.value = lastUsedSelectors;
          }
        } else {
          // Default value
          cssSelectorsInput.value = ".card-body.question-body";
        }
      }
    });

    // Initialize copy and send-to-api buttons with hidden class
    const copyBtn = document.getElementById("copy-btn");
    const apiSendBtn = document.getElementById("send-to-api-btn");
    if (copyBtn) {
      copyBtn.classList.add("hidden");
      copyBtn.classList.remove("visible");
    }
    if (apiSendBtn) {
      apiSendBtn.classList.add("hidden");
      apiSendBtn.classList.remove("visible");
    }

    // Initialize API response container
    const apiResponseContainer = document.getElementById("api-response-container");
    if (apiResponseContainer) {
      apiResponseContainer.classList.add("hidden");
    }

    // Saved selectors panel no longer needed

    // Fallback approach: Try loading each field individually
    setTimeout(() => {
      // Check if fields still need values
      if (document.getElementById("exam-name-input") && !document.getElementById("exam-name-input").value) {
        loadStoredValueToInput(STORAGE_KEYS.LAST_EXAM_NAME, "exam-name-input");
      }

      if (document.getElementById("tags-input") && !document.getElementById("tags-input").value) {
        loadStoredValueToInput(STORAGE_KEYS.LAST_TAGS, "tags-input");
      }

      const textToRemoveInput = document.getElementById("text-to-remove-input");
      if (textToRemoveInput && !textToRemoveInput.value) {
        loadStoredValueToInput(STORAGE_KEYS.LAST_TEXT_TO_REMOVE, "text-to-remove-input");
      }

      const selectorsToRemoveInput = document.getElementById("selectors-to-remove-input");
      if (selectorsToRemoveInput && !selectorsToRemoveInput.value) {
        loadStoredValueToInput(STORAGE_KEYS.LAST_SELECTORS_TO_REMOVE, "selectors-to-remove-input");
      }
    }, 100); // Small delay to ensure DOM is ready

    // Add event listener for Send to API button
    if (apiSendBtn) {
      apiSendBtn.addEventListener("click", async () => {
        const outputText = document.getElementById("output").innerText;

        if (
          outputText &&
          outputText !== 'Click "Extract Text" to get content.' &&
          outputText !== "No content found."
        ) {
          try {
            document.getElementById("output").innerText = "Preparing to send data to API...";

            // Fetch API URL to display it before sending
            chrome.storage.sync.get([STORAGE_KEYS.API_URL], async (result) => {
              if (chrome.runtime.lastError) {
                handleStorageError(chrome.runtime.lastError);
              }

              const apiUrl = result[STORAGE_KEYS.API_URL] || DEFAULT_API_URL;

              // Save the original output text to restore after API operation
              const originalOutputText = outputText;

              // Create a status message but keep the original content in a hidden div
              const statusMessage = `Sending to: ${apiUrl}\n\nPreparing data...`;
              document.getElementById("output").innerHTML = `<div id="api-status-message">${statusMessage}</div><div id="original-output" style="display:none;">${originalOutputText.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</div>`;

              // Short delay to let user see the URL
              setTimeout(async () => {
                try {
                  await sendToAPI(originalOutputText);
                  // Restore original output text after successful API call
                  setTimeout(() => {
                    document.getElementById("output").innerText = originalOutputText;
                  }, 1000);
                } catch (error) {
                  console.error("Error sending to API:", error);
                  // Restore original output text immediately on error
                  document.getElementById("output").innerText = originalOutputText;
                }
              }, 500);
            });
          } catch (error) {
            console.error("Error in API send process:", error);
            document.getElementById("output").innerText = `Error: ${error.message}`;
          }
        } else {
          document.getElementById("output").innerText = "No content to send. Please extract text first.";
        }
      });
    }
  } catch (error) {
    console.error("Error initializing UI:", error);
    // Show error message to user
    const outputElem = document.getElementById("output");
    if (outputElem) {
      outputElem.innerText =
        "Error initializing UI. Please reload the extension.";
    }
  }
});
