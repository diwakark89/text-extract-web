// Storage keys constants
const STORAGE_KEYS = {
    SAVED_SELECTORS: 'saved_selectors',
    LAST_USED_SELECTORS: 'last_used_selectors'
};

// Error handling helper
function handleStorageError(error) {
    console.error('Storage operation failed:', error);
}

// Add selector input field
document.getElementById('add-selector-btn').addEventListener('click', () => {
    addSelectorField();
});

// Toggle saved selectors panel
document.getElementById('manage-saved-btn').addEventListener('click', () => {
    const panel = document.getElementById('saved-selectors-panel');
    if (panel.classList.contains('hidden')) {
        panel.classList.remove('hidden');
        panel.classList.add('visible');
        loadSavedSelectors();
    } else {
        panel.classList.remove('visible');
        panel.classList.add('hidden');
    }
});

// Event delegation for selector actions
document.addEventListener('click', (event) => {
    // Remove selector input field
    if (event.target.classList.contains('remove-selector')) {
        const selectorGroup = event.target.closest('.selector-group');
        if (document.querySelectorAll('.selector-group').length > 1) {
            selectorGroup.remove();
        } else {
            // Don't remove the last selector, just clear it
            selectorGroup.querySelector('.selector-input').value = '';
        }
    }

    // Save selector to storage
    if (event.target.classList.contains('save-selector')) {
        const selectorGroup = event.target.closest('.selector-group');
        const selectorInput = selectorGroup.querySelector('.selector-input');
        const selectorValue = selectorInput.value.trim();

        if (selectorValue) {
            saveSelector(selectorValue);
            // Visual feedback
            event.target.textContent = '✓';
            setTimeout(() => {
                event.target.textContent = '💾';
            }, 1500);
        }
    }

    // Use saved selector
    if (event.target.classList.contains('use-selector')) {
        const selectorItem = event.target.closest('.saved-selector-item');
        const selectorValue = selectorItem.dataset.selector;
        addSelectorField(selectorValue);
    }

    // Delete saved selector
    if (event.target.classList.contains('delete-selector')) {
        const selectorItem = event.target.closest('.saved-selector-item');
        const selectorValue = selectorItem.dataset.selector;
        deleteSelector(selectorValue);
        selectorItem.remove();
    }
});

/**
 * Adds a new selector input field to the UI
 * @param {string} value - Initial value for the selector field
 * @returns {HTMLElement|null} - The created selector group element or null if creation failed
 */
function addSelectorField(value = '') {
    try {
        const container = document.getElementById('selectors-container');
        if (!container) {
            throw new Error('Selectors container not found');
        }

        // Sanitize input value to prevent XSS
        const sanitizedValue = value
            ? value.replace(/[<>"'&]/g, (char) => {
                switch (char) {
                    case '<':
                        return '&lt;';
                    case '>':
                        return '&gt;';
                    case '"':
                        return '&quot;';
                    case "'":
                        return '&#39;';
                    case '&':
                        return '&amp;';
                    default:
                        return char;
                }
            })
            : '';

        const newGroup = document.createElement('div');
        newGroup.className = 'selector-group input-group';
        newGroup.innerHTML = `
                <label>CSS Selector:</label>
                <input type="text" class="selector-input" placeholder="Enter CSS selector" value="${sanitizedValue}">
                <div class="selector-actions">
                    <button class="save-selector" title="Save this selector">💾</button>
                    <button class="remove-selector" title="Remove this selector">×</button>
                </div>
            `;

        container.appendChild(newGroup);
        return newGroup;
    } catch (error) {
        console.error('Error adding selector field:', error);
        return null;
    }
}

/**
 * Saves a selector to storage
 * @param {string} selector - The CSS selector to save
 */
function saveSelector(selector) {
    if (!selector || typeof selector !== 'string' || !selector.trim()) {
        console.warn('Attempted to save an invalid selector');
        return;
    }

    chrome.storage.sync.get([STORAGE_KEYS.SAVED_SELECTORS], (result) => {
        const savedSelectors = result[STORAGE_KEYS.SAVED_SELECTORS] || [];

        // Don't add duplicates
        if (!savedSelectors.includes(selector)) {
            savedSelectors.push(selector);
            chrome.storage.sync.set(
                {[STORAGE_KEYS.SAVED_SELECTORS]: savedSelectors},
                () => {
                    if (chrome.runtime.lastError) {
                        handleStorageError(chrome.runtime.lastError);
                        return;
                    }

                    // Update the saved selectors list if visible
                    if (!document.getElementById('saved-selectors-panel').classList.contains('hidden')) {
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
        const updatedSelectors = savedSelectors.filter(s => s !== selector);

        chrome.storage.sync.set(
            {[STORAGE_KEYS.SAVED_SELECTORS]: updatedSelectors},
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
    const savedSelectorsList = document.getElementById('saved-selectors-list');
    savedSelectorsList.innerHTML = '';

    chrome.storage.sync.get([STORAGE_KEYS.SAVED_SELECTORS], (result) => {
        if (chrome.runtime.lastError) {
            handleStorageError(chrome.runtime.lastError);
            savedSelectorsList.innerHTML = '<p>Error loading saved selectors.</p>';
            return;
        }

        const savedSelectors = result[STORAGE_KEYS.SAVED_SELECTORS] || [];

        if (savedSelectors.length === 0) {
            savedSelectorsList.innerHTML = '<p>No saved selectors yet.</p>';
            return;
        }

        const fragment = document.createDocumentFragment();
        savedSelectors.forEach(selector => {
            const selectorItem = document.createElement('div');
            selectorItem.className = 'saved-selector-item';
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
            throw new Error('Output element not found');
        }

        const selectorInputs = document.querySelectorAll('.selector-input');
        if (!selectorInputs || selectorInputs.length === 0) {
            outputElem.innerText = "No selector inputs found. Please reload the extension.";
            return;
        }

        const selectors = Array.from(selectorInputs)
            .map(input => input.value.trim())
            .filter(selector => selector.length > 0);

        if (selectors.length === 0) {
            outputElem.innerText = "Please enter at least one valid CSS selector.";
            return;
        }

        // Get user extraction options
        const handleRevealButtons = document.getElementById("handle-reveal-buttons").checked;
        const includeHiddenText = document.getElementById("include-hidden-text").checked;

        // Save the current selectors as last used
        chrome.storage.sync.set(
            {[STORAGE_KEYS.LAST_USED_SELECTORS]: selectors},
            () => {
                if (chrome.runtime.lastError) {
                    handleStorageError(chrome.runtime.lastError);
                    // Continue with extraction even if saving fails
                }
            }
        );

        chrome.tabs.query({active: true, currentWindow: true}, (tabs) => {
            const tab = tabs && tabs.length > 0 ? tabs[0] : null;

            if (!tab || !tab.id) {
                outputElem.innerText = "No active tab found. Please try again.";
                return;
            }

            // Update UI to show we're working
            outputElem.innerText = "Extracting text...";

            // Inject and execute the content script
            try {
                chrome.scripting.executeScript({
                    target: {tabId: tab.id},
                    files: ['content-script.js']
                }).then(() => {
                    // First try to reveal hidden content if option is checked
                    if (handleRevealButtons) {
                        // Step 1: First try general simulations of reveal interactions
                        chrome.tabs.sendMessage(tab.id, {
                            action: 'simulateRevealInteractions'
                        }, (simulateResponse) => {
                            console.log('Simulation result:', simulateResponse?.message || 'No response');

                            // Step 2: Try targeted reveal button clicks for each selector
                            const clickPromises = selectors.map(selector => {
                                return new Promise((resolve) => {
                                    chrome.tabs.sendMessage(tab.id, {
                                        action: 'clickRevealButtons',
                                        nearSelector: selector
                                    }, (response) => {
                                        if (chrome.runtime.lastError || !response) {
                                            console.log('Note: Could not handle reveal buttons for selector:', 
                                                selector, chrome.runtime.lastError || 'No response');
                                            resolve();
                                        } else {
                                            console.log('Reveal button handling result for', selector + ':', response.message);
                                            resolve();
                                        }
                                    });
                                });
                            });

                            // Wait for all button operations to complete
                            Promise.all(clickPromises).then(() => {
                                // Wait for any animations or changes to complete
                                setTimeout(() => {
                                    extractText();
                                }, 750); // Increased wait time for better chance of seeing changes
                            });
                        });
                    } else {
                        // Skip reveal button handling
                        extractText();
                    }

                    // Function to extract text from the page
                    function extractText() {
                        // Send message to content script with options
                        chrome.tabs.sendMessage(tab.id, {
                            action: 'extractText',
                            selectors: selectors,
                            options: {
                                includeHiddenText: includeHiddenText
                            }
                        }, (response) => {
                            if (chrome.runtime.lastError) {
                                console.error('Error:', chrome.runtime.lastError);
                                document.getElementById('output').innerText = 
                                    'Error connecting to page. Please refresh and try again.';
                                return;
                            }

                        if (response && response.success) {
                            // Process successful response and update UI directly
                            const outputElem = document.getElementById('output');
                            outputElem.innerText = response.data || "No content found.";

                            // Show copy button if we have content
                            const copyBtn = document.getElementById("copy-btn");
                            if (response.data && response.data.length > 0) {
                                copyBtn.style.display = 'block';
                            }
                        } else {
                            // Handle error
                            const errorMsg = response?.error || 'Unknown error during extraction';
                            console.error('Extraction error:', errorMsg);
                            document.getElementById('output').innerText = 
                                `Error during extraction: ${errorMsg}`;
                        }
                    });
                    }
                }).catch(err => {
                    console.error('Error injecting content script:', err);
                    document.getElementById('output').innerText = 
                        'Error injecting content script. Please refresh and try again.';
                });
            } catch (error) {
                console.error('Error executing script:', error);
                outputElem.innerText = 'Error executing script. Please refresh and try again.';
            }

        });
    } catch (error) {
        console.error('Error during text extraction:', error);
        document.getElementById('output').innerText = "Error during extraction. Please try again.";
    }
});

document.getElementById("copy-btn").addEventListener("click", () => {
    const outputText = document.getElementById("output").innerText;

    if (outputText && outputText !== "Click \"Extract Text\" to get content." && outputText !== "No content found.") {
        navigator.clipboard.writeText(outputText)
            .then(() => {
                const copyBtn = document.getElementById("copy-btn");
                const originalText = copyBtn.innerText;
                copyBtn.innerText = "Copied!";
                setTimeout(() => {
                    copyBtn.innerText = originalText;
                }, 2000);
            })
            .catch(err => {
                console.error('Failed to copy text: ', err);
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
            copyBtn.classList.add('visible');
            copyBtn.classList.remove('hidden');
        } else {
            copyBtn.classList.add('hidden');
            copyBtn.classList.remove('visible');
        }

        // Send acknowledgment response
        sendResponse({status: "success"});
    }
    return true; // Keep the message channel open for asynchronous response
}

// Add the listener when the popup is opened
chrome.runtime.onMessage.addListener(handleExtractedTextMessage);

// Remove the listener when the popup is closed to prevent memory leaks
window.addEventListener('unload', () => {
    try {
        chrome.runtime.onMessage.removeListener(handleExtractedTextMessage);
    } catch (error) {
        console.error('Error removing message listener:', error);
    }
});

// Handle potential errors with the chrome API
chrome.runtime.lastError && console.error('Chrome runtime error:', chrome.runtime.lastError);

/**
 * Initializes the UI when popup opens
 */
document.addEventListener('DOMContentLoaded', () => {
    try {
        // Initialize the selectors container
        const container = document.getElementById('selectors-container');
        if (!container) {
            throw new Error('Selectors container not found');
        }
        container.innerHTML = '';

        // Check for last used selectors in storage
        chrome.storage.sync.get([STORAGE_KEYS.LAST_USED_SELECTORS], (result) => {
            if (chrome.runtime.lastError) {
                handleStorageError(chrome.runtime.lastError);
                // Fall back to default selector
                addSelectorField('.card-body.question-body');
                return;
            }

            const lastUsedSelectors = result[STORAGE_KEYS.LAST_USED_SELECTORS] || ['.card-body.question-body'];

            // Add last used selectors or default
            lastUsedSelectors.forEach(selector => {
                addSelectorField(selector);
            });
        });

        // Initialize copy button with hidden class
        const copyBtn = document.getElementById('copy-btn');
        if (copyBtn) {
            copyBtn.classList.add('hidden');
            copyBtn.classList.remove('visible');
        }

        // Initialize UI visibility states
        const savedSelectorsPanel = document.getElementById('saved-selectors-panel');
        if (savedSelectorsPanel) {
            savedSelectorsPanel.classList.add('hidden');
            savedSelectorsPanel.classList.remove('visible');
        }
    } catch (error) {
        console.error('Error initializing UI:', error);
        // Show error message to user
        const outputElem = document.getElementById('output');
        if (outputElem) {
            outputElem.innerText = 'Error initializing UI. Please reload the extension.';
        }
    }
});
