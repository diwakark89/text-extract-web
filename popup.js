// Storage keys constants
const STORAGE_KEYS = {
  SAVED_SELECTORS: "saved_selectors",
  LAST_USED_SELECTORS: "last_used_selectors",
  LAST_TOPIC: "last_topic",
  LAST_PROMPT: "last_prompt",
  LAST_TEXT_TO_REMOVE: "last_text_to_remove",
  LAST_SELECTORS_TO_REMOVE: "last_selectors_to_remove",
};

// Error handling helper
function handleStorageError(error) {
  console.error("Storage operation failed:", error);
}

// No longer needed - using a comma-separated input field now

// Add save selector button event listener
document.getElementById("save-selector-btn").addEventListener("click", () => {
  try {
    const cssSelectorsInput = document.getElementById("css-selectors-input");
    if (cssSelectorsInput) {
      const selectorsValue = cssSelectorsInput.value.trim();
      if (selectorsValue) {
        // Split by comma and save each selector individually
        const selectors = selectorsValue.split(',').map(s => s.trim()).filter(s => s.length > 0);
        selectors.forEach(selector => saveSelector(selector));

      // Visual feedback
      const saveBtn = document.getElementById("save-selector-btn");
      const originalText = saveBtn.textContent;
      saveBtn.textContent = "✅ Saved!";
      saveBtn.style.background = "#4caf50";
      setTimeout(() => {
        saveBtn.textContent = "📥 Save Current Selectors";
        saveBtn.style.background = "";
      }, 1500);
    }
  }
  } catch (error) {
    console.error("Error saving selectors:", error);
  }
});

// Toggle saved selectors panel
document.getElementById("manage-saved-btn").addEventListener("click", () => {
  const panel = document.getElementById("saved-selectors-panel");
  if (panel.classList.contains("hidden")) {
    panel.classList.remove("hidden");
    panel.classList.add("visible");
    loadSavedSelectors();
  } else {
    panel.classList.remove("visible");
    panel.classList.add("hidden");
  }
});

// Event delegation for selector and text-to-remove actions
document.addEventListener("click", (event) => {
  // No longer needed - using a comma-separated input field now

  // No longer needed - using a comma-separated input field now

  // No longer needed - we now have a dedicated save button

  // Use saved selector
  if (event.target.classList.contains("use-selector")) {
    const selectorItem = event.target.closest(".saved-selector-item");
    const selectorValue = selectorItem.dataset.selector;

    // Add to the comma-separated list
    const cssSelectorsInput = document.getElementById("css-selectors-input");
    if (cssSelectorsInput) {
      const currentValue = cssSelectorsInput.value.trim();
      if (currentValue) {
        // Check if selector already exists in the list
        const selectors = currentValue.split(',').map(s => s.trim());
        if (!selectors.includes(selectorValue)) {
          cssSelectorsInput.value = currentValue + ", " + selectorValue;
        }
      } else {
        cssSelectorsInput.value = selectorValue;
      }
    }
  }

  // Delete saved selector
  if (event.target.classList.contains("delete-selector")) {
    const selectorItem = event.target.closest(".saved-selector-item");
    const selectorValue = selectorItem.dataset.selector;
    deleteSelector(selectorValue);
    selectorItem.remove();
  }
});

// No longer needed - using a comma-separated input field now

// No longer needed - using a comma-separated input field now

/**
 * Saves a selector to storage
 * @param {string} selector - The CSS selector to save
 */
function saveSelector(selector) {
  if (!selector || typeof selector !== "string" || !selector.trim()) {
    console.warn("Attempted to save an invalid selector");
    return;
  }

  chrome.storage.sync.get([STORAGE_KEYS.SAVED_SELECTORS], (result) => {
    const savedSelectors = result[STORAGE_KEYS.SAVED_SELECTORS] || [];

    // Don't add duplicates
    if (!savedSelectors.includes(selector)) {
      savedSelectors.push(selector);
      chrome.storage.sync.set(
        { [STORAGE_KEYS.SAVED_SELECTORS]: savedSelectors },
        () => {
          if (chrome.runtime.lastError) {
            handleStorageError(chrome.runtime.lastError);
            return;
          }

          // Update the saved selectors list if visible
          if (
            !document
              .getElementById("saved-selectors-panel")
              .classList.contains("hidden")
          ) {
            loadSavedSelectors();
          }
        }
      );
    }
  });
}

/**
 * Deletes a selector from storage
 * @param {string} selector - The CSS selector to delete
 */
function deleteSelector(selector) {
  chrome.storage.sync.get([STORAGE_KEYS.SAVED_SELECTORS], (result) => {
    if (chrome.runtime.lastError) {
      handleStorageError(chrome.runtime.lastError);
      return;
    }

    const savedSelectors = result[STORAGE_KEYS.SAVED_SELECTORS] || [];
    const updatedSelectors = savedSelectors.filter((s) => s !== selector);

    chrome.storage.sync.set(
      { [STORAGE_KEYS.SAVED_SELECTORS]: updatedSelectors },
      () => {
        if (chrome.runtime.lastError) {
          handleStorageError(chrome.runtime.lastError);
        }
      }
    );
  });
}

/**
 * Loads and displays saved selectors from storage
 */
function loadSavedSelectors() {
  const savedSelectorsList = document.getElementById("saved-selectors-list");
  savedSelectorsList.innerHTML = "";

  chrome.storage.sync.get([STORAGE_KEYS.SAVED_SELECTORS], (result) => {
    if (chrome.runtime.lastError) {
      handleStorageError(chrome.runtime.lastError);
      savedSelectorsList.innerHTML = "<p>Error loading saved selectors.</p>";
      return;
    }

    const savedSelectors = result[STORAGE_KEYS.SAVED_SELECTORS] || [];

    if (savedSelectors.length === 0) {
      savedSelectorsList.innerHTML = "<p>No saved selectors yet.</p>";
      return;
    }

    const fragment = document.createDocumentFragment();
    savedSelectors.forEach((selector) => {
      const selectorItem = document.createElement("div");
      selectorItem.className = "saved-selector-item";
      selectorItem.dataset.selector = selector;
      selectorItem.innerHTML = `
                    <div class="saved-selector-text" title="${selector}">${selector}</div>
                    <div class="saved-selector-actions">
                        <button class="use-selector" title="Use this selector">➕</button>
                        <button class="delete-selector" title="Delete this selector">🗑️</button>
                    </div>
                `;
      fragment.appendChild(selectorItem);
    });

    savedSelectorsList.appendChild(fragment);
  });
}

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

    // Get topic value
    const topicInput = document.getElementById("topic-input");
    const topic = topicInput.value.trim();
    // Convert to number explicitly to ensure proper type
    const topicNumeric = topic ? Number(topic) : 0;

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
    const handleRevealButtons = document.getElementById(
      "handle-reveal-buttons"
    ).checked;
    const includeHiddenText = document.getElementById(
      "include-hidden-text"
    ).checked;

    // Save the current selectors, topic, prompt, text-to-remove values, and selectors-to-remove as last used
    chrome.storage.sync.set(
      { 
        [STORAGE_KEYS.LAST_USED_SELECTORS]: cssSelectorsValue,
        [STORAGE_KEYS.LAST_TOPIC]: topic,
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
            // First try to reveal hidden content if option is checked
            if (handleRevealButtons) {
              // Step 1: First try general simulations of reveal interactions
              chrome.tabs.sendMessage(
                tab.id,
                {
                  action: "simulateRevealInteractions",
                },
                (simulateResponse) => {
                  // Step 2: Try targeted reveal button clicks for each selector
                  const clickPromises = selectors.map((selector) => {
                    return new Promise((resolve) => {
                      chrome.tabs.sendMessage(
                        tab.id,
                        {
                          action: "clickRevealButtons",
                          nearSelector: selector,
                        },
                        (response) => {
                          if (chrome.runtime.lastError || !response) {
                            resolve();
                          } else {
                            resolve();
                          }
                        }
                      );
                    });
                  });

                  // Wait for all button operations to complete
                  Promise.all(clickPromises).then(() => {
                    // Wait for any animations or changes to complete
                    setTimeout(() => {
                      extractText();
                    }, 750); // Increased wait time for better chance of seeing changes
                  });
                }
              );
            } else {
              // Skip reveal button handling
              extractText();
            }

            // Function to extract text from the page
            function extractText() {
              // Send message to content script with options
              chrome.tabs.sendMessage(
                tab.id,
                {
                  action: "extractText",
                  selectors: selectors,
                  topic: topicNumeric, // Pass as numeric value explicitly
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

                      // If the response data is a string representing JSON, ensure topicId remains a number
                      if (typeof response.data === 'string') {
                        try {
                          // Parse the JSON string to an object
                          const jsonData = JSON.parse(response.data);

                          // Ensure topicId is a number before stringify again
                          if (jsonData && 'topicId' in jsonData) {
                            jsonData.topicId = Number(jsonData.topicId);
                          }

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

                      // Show copy button if we have content
                      const copyBtn = document.getElementById("copy-btn");
                      if (response.data && response.data.length > 0) {
                        copyBtn.style.display = "block";
                        copyBtn.classList.add("visible");
                        copyBtn.classList.remove("hidden");
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

// Define the message handler function separately for better cleanup
function handleExtractedTextMessage(message, sender, sendResponse) {
  if (message.type === "EXTRACTED_TEXT") {
    const outputElem = document.getElementById("output");
    const copyBtn = document.getElementById("copy-btn");

    outputElem.innerText = message.payload || "No content found.";

    // Show or hide the copy button based on whether there is content
    if (message.payload && message.payload.length > 0) {
      copyBtn.classList.add("visible");
      copyBtn.classList.remove("hidden");
    } else {
      copyBtn.classList.add("hidden");
      copyBtn.classList.remove("visible");
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
 * Initializes the UI when popup opens
 */
document.addEventListener("DOMContentLoaded", () => {
  try {
    // No need to initialize selectors container anymore since we use a single input field

    // No need to initialize text-to-remove container anymore since we use a single input field

    // Load stored values (selectors, topic, prompt, text-to-remove, selectors-to-remove)
    chrome.storage.sync.get([
      STORAGE_KEYS.LAST_USED_SELECTORS,
      STORAGE_KEYS.LAST_TOPIC,
      STORAGE_KEYS.LAST_PROMPT,
      STORAGE_KEYS.LAST_TEXT_TO_REMOVE,
      STORAGE_KEYS.LAST_SELECTORS_TO_REMOVE
    ], (result) => {
      if (chrome.runtime.lastError) {
        handleStorageError(chrome.runtime.lastError);
        // Fall back to default selector value (now handled in HTML)
        return;
      }

      // Set topic input value if available
      const topicInput = document.getElementById("topic-input");
      if (topicInput && result[STORAGE_KEYS.LAST_TOPIC]) {
        topicInput.value = result[STORAGE_KEYS.LAST_TOPIC];
      }

      // Set prompt input value if available
      const promptInput = document.getElementById("prompt-input");
      if (promptInput && result[STORAGE_KEYS.LAST_PROMPT]) {
        promptInput.value = result[STORAGE_KEYS.LAST_PROMPT];
      }

      // Set text-to-remove input value if available
      const textToRemoveInput = document.getElementById("text-to-remove-input");
      if (textToRemoveInput && result[STORAGE_KEYS.LAST_TEXT_TO_REMOVE]) {
        textToRemoveInput.value = result[STORAGE_KEYS.LAST_TEXT_TO_REMOVE];
      }

      // Set selectors-to-remove input value if available
      const selectorsToRemoveInput = document.getElementById("selectors-to-remove-input");
      if (selectorsToRemoveInput && result[STORAGE_KEYS.LAST_SELECTORS_TO_REMOVE]) {
        // If it's an array (from previous version), join with commas
        if (Array.isArray(result[STORAGE_KEYS.LAST_SELECTORS_TO_REMOVE])) {
          selectorsToRemoveInput.value = result[STORAGE_KEYS.LAST_SELECTORS_TO_REMOVE].join(', ');
        } else {
          // Otherwise use the string directly
          selectorsToRemoveInput.value = result[STORAGE_KEYS.LAST_SELECTORS_TO_REMOVE];
        }
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

    // Initialize copy button with hidden class
    const copyBtn = document.getElementById("copy-btn");
    if (copyBtn) {
      copyBtn.classList.add("hidden");
      copyBtn.classList.remove("visible");
    }

    // Initialize UI visibility states
    const savedSelectorsPanel = document.getElementById(
      "saved-selectors-panel"
    );
    if (savedSelectorsPanel) {
      savedSelectorsPanel.classList.add("hidden");
      savedSelectorsPanel.classList.remove("visible");
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
