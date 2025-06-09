/**
 * Text Extractor Extension - Background Service Worker
 * Handles message passing and extension lifecycle events
 */
// Background script for the Question Text Extractor extension

// Listen for network errors
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "apiCall") {
    // Handle API call using background script to avoid CORS issues
    // If using the local API endpoint, ensure we're using the right URL
    const finalUrl = message.url.includes('localhost') || message.url.includes('127.0.0.1')
      ? message.url
      : 'http://localhost:8888/api/v1/manage/mcq/save/text';

    fetch(finalUrl, {
      method: message.method || 'POST',
      headers: message.headers || {
        'Content-Type': 'application/json'
      },
      body: message.body,
      // We can use different mode here since background has different privileges
      mode: 'cors',
      credentials: 'include' // Include credentials for local API
    })
    .then(response => {
      return response.text().then(text => {
        return {
          ok: response.ok,
          status: response.status,
          statusText: response.statusText,
          text: text
        };
      });
    })
    .then(result => {
      sendResponse({success: true, data: result});
    })
    .catch(error => {
      console.error("API call error:", error);
      sendResponse({success: false, error: error.toString()});
    });

    return true; // Required to use sendResponse asynchronously
  }
});

// Extension installation/update handler
chrome.runtime.onInstalled.addListener((details) => {
  // Handle installation/update events silently
});
/**
 * Handles extension installation or update
 */
chrome.runtime.onInstalled.addListener((details) => {
  try {
    if (details.reason === "install") {
      // Initialize default storage values
      chrome.storage.sync.set({
        saved_selectors: [],
        last_used_selectors: [".card-body.question-body"],
      });
    } else if (details.reason === "update") {
      // Migrate storage data if needed between versions
    }
  } catch (error) {
    console.error("Error during extension installation/update:", error);
  }
});

// Listen for messages from content scripts or popup
chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
  // Always send a response to avoid hanging connections
  sendResponse({ status: "received" });
  return false; // No async response needed
});
