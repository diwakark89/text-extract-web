// Storage keys constants
const STORAGE_KEYS = {
  LAST_QUESTION_SELECTOR: "last_question_selector",
  LAST_QUESTION_CHILD_SELECTOR: "last_question_child_selector",
  LAST_OPTIONS_SELECTOR: "last_options_selector",
  LAST_OPTIONS_CHILD_SELECTOR: "last_options_child_selector",
  LAST_ANSWER_SELECTOR: "last_answer_selector",
  LAST_ANSWER_CHILD_SELECTOR: "last_answer_child_selector",
  LAST_PROMPT: "last_prompt",
  LAST_TEXT_TO_REMOVE: "last_text_to_remove",
  LAST_SELECTORS_TO_REMOVE: "last_selectors_to_remove",
  LAST_START_INDEX: "last_start_index",
};

// Error handling helper
function handleStorageError(error) {
  console.error("Storage operation failed:", error);
}

// No longer needed - using a comma-separated input field now

// Save selector functionality is now automatic through the extract button
// and when the popup is closed. No manual save needed.

// Automatically save question selector when it changes
document
  .getElementById("question-selector-input")
  .addEventListener("change", (event) => {
    try {
      const selectorValue = event.target.value.trim();
      chrome.storage.sync.set(
        { [STORAGE_KEYS.LAST_QUESTION_SELECTOR]: selectorValue },
        () => {
          if (chrome.runtime.lastError) {
            handleStorageError(chrome.runtime.lastError);
          }
        },
      );
    } catch (error) {
      console.error("Error auto-saving question selector:", error);
    }
  });

// Automatically save question child selector when it changes
document
  .getElementById("question-child-selector-input")
  .addEventListener("change", (event) => {
    try {
      const selectorValue = event.target.value.trim();
      chrome.storage.sync.set(
        { [STORAGE_KEYS.LAST_QUESTION_CHILD_SELECTOR]: selectorValue },
        () => {
          if (chrome.runtime.lastError) {
            handleStorageError(chrome.runtime.lastError);
          }
        },
      );
    } catch (error) {
      console.error("Error auto-saving question child selector:", error);
    }
  });

// Automatically save options selector when it changes
document
  .getElementById("options-selector-input")
  .addEventListener("change", (event) => {
    try {
      const selectorValue = event.target.value.trim();
      chrome.storage.sync.set(
        { [STORAGE_KEYS.LAST_OPTIONS_SELECTOR]: selectorValue },
        () => {
          if (chrome.runtime.lastError) {
            handleStorageError(chrome.runtime.lastError);
          }
        },
      );
    } catch (error) {
      console.error("Error auto-saving options selector:", error);
    }
  });

// Automatically save options child selector when it changes
document
  .getElementById("options-child-selector-input")
  .addEventListener("change", (event) => {
    try {
      const selectorValue = event.target.value.trim();
      chrome.storage.sync.set(
        { [STORAGE_KEYS.LAST_OPTIONS_CHILD_SELECTOR]: selectorValue },
        () => {
          if (chrome.runtime.lastError) {
            handleStorageError(chrome.runtime.lastError);
          }
        },
      );
    } catch (error) {
      console.error("Error auto-saving options child selector:", error);
    }
  });

// Automatically save answer selector when it changes
document
  .getElementById("answer-selector-input")
  .addEventListener("change", (event) => {
    try {
      const selectorValue = event.target.value.trim();
      chrome.storage.sync.set(
        { [STORAGE_KEYS.LAST_ANSWER_SELECTOR]: selectorValue },
        () => {
          if (chrome.runtime.lastError) {
            handleStorageError(chrome.runtime.lastError);
          }
        },
      );
    } catch (error) {
      console.error("Error auto-saving answer selector:", error);
    }
  });

// Automatically save answer child selector when it changes
document
  .getElementById("answer-child-selector-input")
  .addEventListener("change", (event) => {
    try {
      const selectorValue = event.target.value.trim();
      chrome.storage.sync.set(
        { [STORAGE_KEYS.LAST_ANSWER_CHILD_SELECTOR]: selectorValue },
        () => {
          if (chrome.runtime.lastError) {
            handleStorageError(chrome.runtime.lastError);
          }
        },
      );
    } catch (error) {
      console.error("Error auto-saving answer child selector:", error);
    }
  });

// Automatically save selectors-to-remove values when they change
document
  .getElementById("selectors-to-remove-input")
  .addEventListener("change", (event) => {
    try {
      const selectorsToRemoveValue = event.target.value.trim();
      // Save current value to storage
      chrome.storage.sync.set(
        { [STORAGE_KEYS.LAST_SELECTORS_TO_REMOVE]: selectorsToRemoveValue },
        () => {
          if (chrome.runtime.lastError) {
            handleStorageError(chrome.runtime.lastError);
          }
        },
      );
    } catch (error) {
      console.error("Error auto-saving selectors-to-remove:", error);
    }
  });

// Automatically save text-to-remove values when they change
document
  .getElementById("text-to-remove-input")
  .addEventListener("change", (event) => {
    try {
      const textToRemoveValue = event.target.value.trim();
      // Save current value to storage
      chrome.storage.sync.set(
        { [STORAGE_KEYS.LAST_TEXT_TO_REMOVE]: textToRemoveValue },
        () => {
          if (chrome.runtime.lastError) {
            handleStorageError(chrome.runtime.lastError);
          }
        },
      );
    } catch (error) {
      console.error("Error auto-saving text-to-remove:", error);
    }
  });

// Automatically save start index value when it changes
document
  .getElementById("start-index-input")
  .addEventListener("change", (event) => {
    try {
      const startIndexValue = event.target.value.trim();
      chrome.storage.sync.set(
        { [STORAGE_KEYS.LAST_START_INDEX]: startIndexValue },
        () => {
          if (chrome.runtime.lastError) {
            handleStorageError(chrome.runtime.lastError);
          }
        },
      );
    } catch (error) {
      console.error("Error auto-saving start index:", error);
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

    const questionSelectorInput = document.getElementById(
      "question-selector-input",
    );
    const questionChildSelectorInput = document.getElementById(
      "question-child-selector-input",
    );
    const optionsSelectorInput = document.getElementById(
      "options-selector-input",
    );
    const optionsChildSelectorInput = document.getElementById(
      "options-child-selector-input",
    );
    const answerSelectorInput = document.getElementById(
      "answer-selector-input",
    );
    const answerChildSelectorInput = document.getElementById(
      "answer-child-selector-input",
    );

    if (
      !questionSelectorInput ||
      !optionsSelectorInput ||
      !answerSelectorInput
    ) {
      outputElem.innerText =
        "Selector inputs not found. Please reload the extension.";
      return;
    }

    const questionSelector = questionSelectorInput.value.trim();
    const questionChildSelector = questionChildSelectorInput
      ? questionChildSelectorInput.value.trim()
      : "";
    const optionsSelector = optionsSelectorInput.value.trim();
    const optionsChildSelector = optionsChildSelectorInput
      ? optionsChildSelectorInput.value.trim()
      : "";
    const answerSelector = answerSelectorInput.value.trim();
    const answerChildSelector = answerChildSelectorInput
      ? answerChildSelectorInput.value.trim()
      : "";

    if (!questionSelector || !optionsSelector || !answerSelector) {
      outputElem.innerText =
        "Please enter all three CSS selectors (Question, Options, Answer).";
      return;
    }

    // Get prompt value
    const prompt = document.getElementById("prompt-input").value.trim();

    // Get start index (1-based)
    const startIndexInput = document.getElementById("start-index-input");
    const startIndexRawValue = startIndexInput
      ? startIndexInput.value.trim()
      : "";
    let startIndex = 1;

    if (startIndexRawValue) {
      if (!/^\d+$/.test(startIndexRawValue) || Number(startIndexRawValue) < 1) {
        outputElem.innerText =
          "Please enter a valid Start Index (1 or higher).";
        return;
      }
      startIndex = Number(startIndexRawValue);
    }

    if (startIndexInput) {
      startIndexInput.value = String(startIndex);
    }

    // Get comma-separated text-to-remove values
    const textToRemoveInput = document.getElementById("text-to-remove-input");
    const textToRemoveValue = textToRemoveInput.value.trim();
    const textToRemoveValues = textToRemoveValue
      ? textToRemoveValue
          .split(",")
          .map((item) => item.trim())
          .filter((item) => item.length > 0)
      : [];

    // Get comma-separated selectors-to-remove values
    const selectorsToRemoveInput = document.getElementById(
      "selectors-to-remove-input",
    );
    const selectorsToRemoveValue = selectorsToRemoveInput.value.trim();
    const selectorsToRemove = selectorsToRemoveValue
      ? selectorsToRemoveValue
          .split(",")
          .map((item) => item.trim())
          .filter((item) => item.length > 0)
      : [];

    // Get user extraction options
    const includeHiddenText = document.getElementById(
      "include-hidden-text",
    ).checked;

    // Save the current selectors, prompt, text-to-remove values, and selectors-to-remove as last used
    chrome.storage.sync.set(
      {
        [STORAGE_KEYS.LAST_QUESTION_SELECTOR]: questionSelector,
        [STORAGE_KEYS.LAST_QUESTION_CHILD_SELECTOR]: questionChildSelector,
        [STORAGE_KEYS.LAST_OPTIONS_SELECTOR]: optionsSelector,
        [STORAGE_KEYS.LAST_OPTIONS_CHILD_SELECTOR]: optionsChildSelector,
        [STORAGE_KEYS.LAST_ANSWER_SELECTOR]: answerSelector,
        [STORAGE_KEYS.LAST_ANSWER_CHILD_SELECTOR]: answerChildSelector,
        [STORAGE_KEYS.LAST_PROMPT]: prompt,
        [STORAGE_KEYS.LAST_START_INDEX]: String(startIndex),
        [STORAGE_KEYS.LAST_TEXT_TO_REMOVE]: textToRemoveValue,
        [STORAGE_KEYS.LAST_SELECTORS_TO_REMOVE]: selectorsToRemoveValue,
      },
      () => {
        if (chrome.runtime.lastError) {
          handleStorageError(chrome.runtime.lastError);
          // Continue with extraction even if saving fails
        }
      },
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
                  questionSelector: questionSelector,
                  optionsSelector: optionsSelector,
                  answerSelector: answerSelector,
                  prompt: prompt,
                  startIndex: startIndex,
                  textToRemoveValues: textToRemoveValues,
                  selectorsToRemove: selectorsToRemove, // Pass the selectors to remove as array
                  options: {
                    includeHiddenText: includeHiddenText,
                    questionChildSelector: questionChildSelector,
                    optionsChildSelector: optionsChildSelector,
                    answerChildSelector: answerChildSelector,
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
                      if (typeof response.data === "string") {
                        try {
                          // Parse the JSON string to an object
                          const jsonData = JSON.parse(response.data);

                          // Convert back to a formatted string
                          outputElem.innerText = JSON.stringify(
                            jsonData,
                            null,
                            2,
                          );
                        } catch (e) {
                          // If parsing fails, just use the original string
                          console.error("Error parsing JSON response:", e);
                          outputElem.innerText =
                            response.data || "No content found.";
                        }
                      } else {
                        // Just use the data as is
                        outputElem.innerText =
                          response.data || "No content found.";
                      }

                      // Show copy button if we have content
                      const copyBtn = document.getElementById("copy-btn");
                      if (response.data && response.data.length > 0) {
                        if (copyBtn) {
                          copyBtn.style.display = "inline-block";
                          copyBtn.classList.add("visible");
                          copyBtn.classList.remove("hidden");
                        }
                      }
                    } catch (e) {
                      console.error("Error processing response:", e);
                      document.getElementById("output").innerText =
                        response.data || "No content found.";
                    }
                  } else {
                    // Handle error
                    const errorMsg =
                      response?.error || "Unknown error during extraction";
                    console.error("Extraction error:", errorMsg);
                    document.getElementById("output").innerText =
                      `Error during extraction: ${errorMsg}`;
                  }
                },
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
        inputElement.value = storedValue.join(", ");
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

    // Load stored values (selectors, prompt, text-to-remove, selectors-to-remove)
    chrome.storage.sync.get(
      [
        STORAGE_KEYS.LAST_QUESTION_SELECTOR,
        STORAGE_KEYS.LAST_QUESTION_CHILD_SELECTOR,
        STORAGE_KEYS.LAST_OPTIONS_SELECTOR,
        STORAGE_KEYS.LAST_OPTIONS_CHILD_SELECTOR,
        STORAGE_KEYS.LAST_ANSWER_SELECTOR,
        STORAGE_KEYS.LAST_ANSWER_CHILD_SELECTOR,
        STORAGE_KEYS.LAST_PROMPT,
        STORAGE_KEYS.LAST_START_INDEX,
        STORAGE_KEYS.LAST_TEXT_TO_REMOVE,
        STORAGE_KEYS.LAST_SELECTORS_TO_REMOVE,
      ],
      (result) => {
        if (chrome.runtime.lastError) {
          handleStorageError(chrome.runtime.lastError);
          // Fall back to default selector value (now handled in HTML)
          return;
        }

        // Set prompt input value if available
        const promptInput = document.getElementById("prompt-input");
        if (promptInput) {
          if (result[STORAGE_KEYS.LAST_PROMPT] !== undefined) {
            promptInput.value = result[STORAGE_KEYS.LAST_PROMPT];
          }
        } else {
          console.warn("Prompt input element not found");
        }

        // Set start index input value if available
        const startIndexInput = document.getElementById("start-index-input");
        if (startIndexInput) {
          if (result[STORAGE_KEYS.LAST_START_INDEX] !== undefined) {
            startIndexInput.value = result[STORAGE_KEYS.LAST_START_INDEX];
          }
        } else {
          console.warn("Start index input element not found");
        }

        // Set text-to-remove input value if available
        const textToRemoveInput = document.getElementById(
          "text-to-remove-input",
        );
        if (textToRemoveInput) {
          if (result[STORAGE_KEYS.LAST_TEXT_TO_REMOVE] !== undefined) {
            textToRemoveInput.value = result[STORAGE_KEYS.LAST_TEXT_TO_REMOVE];
          }
        } else {
          console.warn("Text-to-remove input element not found");
        }

        // Set selectors-to-remove input value if available
        const selectorsToRemoveInput = document.getElementById(
          "selectors-to-remove-input",
        );
        if (selectorsToRemoveInput) {
          if (result[STORAGE_KEYS.LAST_SELECTORS_TO_REMOVE] !== undefined) {
            // If it's an array (from previous version), join with commas
            if (Array.isArray(result[STORAGE_KEYS.LAST_SELECTORS_TO_REMOVE])) {
              selectorsToRemoveInput.value =
                result[STORAGE_KEYS.LAST_SELECTORS_TO_REMOVE].join(", ");
            } else {
              // Otherwise use the string directly
              selectorsToRemoveInput.value =
                result[STORAGE_KEYS.LAST_SELECTORS_TO_REMOVE];
            }
          }
        } else {
          console.warn("Selectors-to-remove input element not found");
        }

        // Set selector input values if available
        const questionSelectorInput = document.getElementById(
          "question-selector-input",
        );
        if (
          questionSelectorInput &&
          result[STORAGE_KEYS.LAST_QUESTION_SELECTOR]
        ) {
          questionSelectorInput.value =
            result[STORAGE_KEYS.LAST_QUESTION_SELECTOR];
        }

        const optionsSelectorInput = document.getElementById(
          "options-selector-input",
        );
        if (
          optionsSelectorInput &&
          result[STORAGE_KEYS.LAST_OPTIONS_SELECTOR]
        ) {
          optionsSelectorInput.value =
            result[STORAGE_KEYS.LAST_OPTIONS_SELECTOR];
        }

        const questionChildSelectorInput = document.getElementById(
          "question-child-selector-input",
        );
        if (
          questionChildSelectorInput &&
          result[STORAGE_KEYS.LAST_QUESTION_CHILD_SELECTOR]
        ) {
          questionChildSelectorInput.value =
            result[STORAGE_KEYS.LAST_QUESTION_CHILD_SELECTOR];
        }

        const optionsChildSelectorInput = document.getElementById(
          "options-child-selector-input",
        );
        if (
          optionsChildSelectorInput &&
          result[STORAGE_KEYS.LAST_OPTIONS_CHILD_SELECTOR]
        ) {
          optionsChildSelectorInput.value =
            result[STORAGE_KEYS.LAST_OPTIONS_CHILD_SELECTOR];
        }

        const answerSelectorInput = document.getElementById(
          "answer-selector-input",
        );
        if (answerSelectorInput && result[STORAGE_KEYS.LAST_ANSWER_SELECTOR]) {
          answerSelectorInput.value = result[STORAGE_KEYS.LAST_ANSWER_SELECTOR];
        }

        const answerChildSelectorInput = document.getElementById(
          "answer-child-selector-input",
        );
        if (
          answerChildSelectorInput &&
          result[STORAGE_KEYS.LAST_ANSWER_CHILD_SELECTOR]
        ) {
          answerChildSelectorInput.value =
            result[STORAGE_KEYS.LAST_ANSWER_CHILD_SELECTOR];
        }
      },
    );

    // Initialize copy button with hidden class
    const copyBtn = document.getElementById("copy-btn");
    if (copyBtn) {
      copyBtn.classList.add("hidden");
      copyBtn.classList.remove("visible");
    }

    // Saved selectors panel no longer needed

    // Fallback approach: Try loading each field individually
    setTimeout(() => {
      // Check if fields still need values
      if (
        document.getElementById("start-index-input") &&
        !document.getElementById("start-index-input").value
      ) {
        loadStoredValueToInput(
          STORAGE_KEYS.LAST_START_INDEX,
          "start-index-input",
        );
      }

      const questionChildSelectorInput = document.getElementById(
        "question-child-selector-input",
      );
      if (questionChildSelectorInput && !questionChildSelectorInput.value) {
        loadStoredValueToInput(
          STORAGE_KEYS.LAST_QUESTION_CHILD_SELECTOR,
          "question-child-selector-input",
        );
      }

      const optionsChildSelectorInput = document.getElementById(
        "options-child-selector-input",
      );
      if (optionsChildSelectorInput && !optionsChildSelectorInput.value) {
        loadStoredValueToInput(
          STORAGE_KEYS.LAST_OPTIONS_CHILD_SELECTOR,
          "options-child-selector-input",
        );
      }

      const answerChildSelectorInput = document.getElementById(
        "answer-child-selector-input",
      );
      if (answerChildSelectorInput && !answerChildSelectorInput.value) {
        loadStoredValueToInput(
          STORAGE_KEYS.LAST_ANSWER_CHILD_SELECTOR,
          "answer-child-selector-input",
        );
      }

      const textToRemoveInput = document.getElementById("text-to-remove-input");
      if (textToRemoveInput && !textToRemoveInput.value) {
        loadStoredValueToInput(
          STORAGE_KEYS.LAST_TEXT_TO_REMOVE,
          "text-to-remove-input",
        );
      }

      const selectorsToRemoveInput = document.getElementById(
        "selectors-to-remove-input",
      );
      if (selectorsToRemoveInput && !selectorsToRemoveInput.value) {
        loadStoredValueToInput(
          STORAGE_KEYS.LAST_SELECTORS_TO_REMOVE,
          "selectors-to-remove-input",
        );
      }
    }, 100); // Small delay to ensure DOM is ready
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
