// This event listener was duplicated and incorrect - removing it
// The correct implementation is in the saveOptions function below
// Storage keys constants (must match popup.js)
const STORAGE_KEYS = {
  SAVED_SELECTORS: "saved_selectors",
  LAST_USED_SELECTORS: "last_used_selectors",
  LAST_TOPIC: "last_topic",
  LAST_PROMPT: "last_prompt",
  LAST_TEXT_TO_REMOVE: "last_text_to_remove",
  LAST_SELECTORS_TO_REMOVE: "last_selectors_to_remove",
  API_URL: "api_url"
};

// Default API URL
const DEFAULT_API_URL = "http://localhost:8888/api/v1/manage/mcq/save/text";

// Save options to chrome.storage
function saveOptions() {
  const defaultPrompt = document.getElementById('default-prompt').value;
  const apiUrl = document.getElementById('api-url').value || 'http://localhost:8888/api/v1/manage/mcq/save/text';

  chrome.storage.sync.set(
    {
      'default_prompt': defaultPrompt,
      [STORAGE_KEYS.API_URL]: apiUrl
    },
    () => {
      // Update status to let user know options were saved
      const status = document.getElementById('status');
      if (status) {
        status.textContent = 'Options saved.';
        setTimeout(() => {
          status.textContent = '';
        }, 2000);
      }
    }
  );
}

// Restore options from chrome.storage
function restoreOptions() {
  chrome.storage.sync.get(
    {
      'default_prompt': '',
      [STORAGE_KEYS.API_URL]: DEFAULT_API_URL
    },
    (items) => {
      document.getElementById('default-prompt').value = items.default_prompt;
      document.getElementById('api-url').value = items[STORAGE_KEYS.API_URL];
    }
  );
}

// Initialize the options page
document.addEventListener('DOMContentLoaded', () => {
  // Restore saved options
  restoreOptions();

  // Add event listeners
  document.getElementById('save-btn').addEventListener('click', saveOptions);
});
// Note: This event listener is no longer needed as it's duplicated
// The restoreOptions function above handles this functionality correctly
