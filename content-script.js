/**
 * Content script for Question Text Extractor extension
 *
 * This script is injected into web pages to extract text from specified elements
 * using CSS selectors. It communicates with the popup via Chrome's messaging API.
 */

// Listen for messages from the popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  console.log("Content script received message:", request);

  if (request.action === "extractText") {
    if (!request.selectors || !Array.isArray(request.selectors)) {
      sendResponse({
        success: false,
        error: "Invalid selectors provided",
      });
      return true;
    }

    const options = request.options || {};
    // Default to including hidden text if not specified
    const includeHiddenText = options.includeHiddenText !== false;

    // Get topic, prompt, and text-to-remove values if provided
    const topic = request.topic || "";
    console.log("Content script received topic:", topic, typeof topic);
    // Additional checks for topic value
    if (topic) {
      console.log("Topic value details:", {
        value: topic,
        type: typeof topic,
        asNumber: Number(topic),
        isNaN: isNaN(Number(topic)),
        parsed: parseInt(topic, 10)
      });
    }
    const prompt = request.prompt || "";
    const textToRemoveValues = request.textToRemoveValues || [];

    // Extract text based on provided selectors and options
    extractTextFromSelectors(request.selectors, { includeHiddenText, topic, prompt, textToRemoveValues })
      .then((result) => {
        sendResponse({
          success: true,
          data: result,
        });
      })
      .catch((error) => {
        sendResponse({
          success: false,
          error: error.message || "Unknown error during extraction",
        });
      });

    // Return true to indicate we'll respond asynchronously
    return true;
  } else {
    // Send response for unsupported actions
    sendResponse({
      success: false,
      error: "Unsupported action",
    });
    return false;
  }
});

/**
 * Extracts text from DOM elements matching the provided CSS selectors
 * @param {string[]} selectors - Array of CSS selectors to target
 * @param {Object} options - Extraction options
 * @param {boolean} options.includeHiddenText - Whether to include text from hidden elements
 * @param {string} options.topic - Topic ID to include with the extracted text
 * @param {string} options.prompt - Prompt text to include with the extracted text
 * @param {string[]} options.textToRemoveValues - Array of text patterns to remove from the extracted content
 * @returns {Promise<string>} - Promise resolving to formatted extracted text
 */
async function extractTextFromSelectors(
  selectors,
  options = { includeHiddenText: true, topic: "", prompt: "", textToRemoveValues: [] }
) {
  try {
    let allExtractedText = [];

    // Process each selector
    for (const selector of selectors) {
      try {
        // Find all elements matching the selector
        const elements = document.querySelectorAll(selector);

        // Step 1: Try to reveal hidden content first
        await attemptToRevealHiddenContent(elements);

        // Step 2: Extract text from each element, including hidden ones
        const extractedText = Array.from(elements)
          .map((el) => {
            // Always try to get both hidden and visible content
            const visibleText = el.innerText.trim();
            const hiddenText = extractHiddenText(el);

            // Combine all text, using visible text if available
            return visibleText || hiddenText || "";
          })
          .filter((text) => text.length > 0);

        // Step 3: Look for additional hidden elements within parent containers
        const parentElements = new Set();
        elements.forEach((el) => {
          if (el.parentElement) parentElements.add(el.parentElement);
        });

        // Format and add each extracted text item individually to the array
        // This way each extracted element becomes its own item in mcqTextList
        if (extractedText.length > 0) {
          extractedText.forEach(text => {
            allExtractedText.push(text);
          });
        }
      } catch (error) {
        console.error(`Error with selector ${selector}:`, error);
      }
    }

    // Process text-to-remove patterns
    let extractedText = allExtractedText.join("\n\n---\n\n");

    if (options.textToRemoveValues && options.textToRemoveValues.length > 0) {
      options.textToRemoveValues.forEach(pattern => {
        if (pattern) {
          try {
            // Escape special regex characters to treat the pattern as literal text
            const safePattern = pattern.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
            extractedText = extractedText.replace(new RegExp(safePattern, 'g'), '');
          } catch (e) {
            // Fallback to simple string replacement if regex fails
            extractedText = extractedText.split(pattern).join('');
          }
        }
      });
    }

    // Split the extracted text into an array of strings
    const mcqTextArray = [];
    if (extractedText) {
      // Split by the section separator
      const sections = extractedText.split('\n\n---\n\n');
      for (const section of sections) {
        if (section.trim()) {
          mcqTextArray.push(section.trim());
        }
      }
    }

    // If no mcqText was found, add a placeholder
    if (mcqTextArray.length === 0) {
      mcqTextArray.push("No content found with the provided selectors.");
    }

    // Create a JSON response with the new required format
    // Debug: log the topic value before processing
    console.log('Topic value before final processing:', options.topic, typeof options.topic);

    // Force topic to be a number and ensure it's not 0 unless actually empty
    let topicIdValue = 0;
    if (options.topic !== undefined && options.topic !== null) {
      // Convert to number directly
      topicIdValue = Number(options.topic);
      console.log('Converted topic value:', topicIdValue, typeof topicIdValue);

      // If it's NaN, try parsing it as an integer
      if (isNaN(topicIdValue)) {
        try {
          // Try parsing as integer with different base
          topicIdValue = parseInt(String(options.topic).trim(), 10);
          console.log('Parsed as int:', topicIdValue);
        } catch (e) {
          console.error('Error parsing topic:', e);
          topicIdValue = 0;
        }
      }
    }

    // Create response object with the properly processed topic ID
    const responseObject = {
      prompt: options.prompt || "",
      topicId: topicIdValue,
      mcqTextList: mcqTextArray,
      unwantedTexts: options.textToRemoveValues || [],
      tagList: [123, 456],  // Hardcoded as specified
      userId: 2,            // Hardcoded as specified
      isPublic: true,       // Hardcoded as specified
      difficultyLevel: "EASY" // Hardcoded as specified
    };

    // Debug: Log the final object to ensure topicId is set correctly
    console.log('Final response object:', responseObject);

    // Debug: Log the stringified JSON
    const jsonString = JSON.stringify(responseObject, null, 2);
    console.log('Stringified JSON:', jsonString);

    // Double-check that topicId is still a number after parsing
    const parsedBack = JSON.parse(jsonString);
    console.log('Parsed back topicId:', parsedBack.topicId, typeof parsedBack.topicId);

    return jsonString;
  } catch (error) {
    console.error("Error extracting text:", error);
    throw error;
  }
}

/**
 * Attempts to reveal hidden content by interacting with "reveal" buttons
 * @param {NodeList} elements - Elements to check for reveal buttons
 * @returns {Promise<void>}
 */
async function attemptToRevealHiddenContent(elements) {
  try {

    const relevantButtons = [];

    // Find buttons that might reveal content near our elements
    elements.forEach((element) => {
      // Check for buttons within the element
      element
        .querySelectorAll('button, a, .btn, [role="button"]')
        .forEach((btn) => {
          relevantButtons.push(btn);
        });

      // Check for buttons that are siblings
      if (element.parentElement) {
        element.parentElement
          .querySelectorAll('button, a, .btn, [role="button"]')
          .forEach((btn) => {
            if (!relevantButtons.includes(btn)) {
              relevantButtons.push(btn);
            }
          });
      }
    });

    // Filter for likely reveal buttons
    const revealButtons = relevantButtons.filter((btn) => {
      const text = btn.textContent?.toLowerCase() || "";
      const hasRevealText = [
        "show",
        "more",
        "reveal",
        "expand",
        "view",
        "see all",
        "read",
      ].some((keyword) => text.includes(keyword));
      const hasRevealAttr =
        btn.getAttribute("aria-expanded") === "false" ||
        btn.getAttribute("aria-controls") ||
        btn.classList.contains("show-more") ||
        btn.classList.contains("expand");
      return hasRevealText || hasRevealAttr;
    });

    // Click the reveal buttons
    for (const btn of revealButtons) {
      try {
        btn.click();
        // Wait a bit for content to appear
        await new Promise((r) => setTimeout(r, 100));
      } catch (e) {
        console.warn("Failed to click reveal button:", e);
      }
    }
  } catch (error) {
    console.error("Error revealing hidden content:", error);
  }
}

/**
 * Extracts text from hidden elements
 * @param {HTMLElement} element - Element to extract hidden text from
 * @returns {string} - Extracted text content
 */
function extractHiddenText(element) {
  // Check for hidden content
  let hiddenContent = "";

  // Try several methods to get hidden text
  const isHidden = window.getComputedStyle(element).display === "none";

  if (isHidden) {
    // Method 1: Get textContent (works for hidden elements)
    hiddenContent = element.textContent?.trim() || "";

    // Method 2: If no text content, try to extract from HTML
    if (!hiddenContent) {
      hiddenContent =
        element.innerHTML
          ?.replace(/<style[^>]*>[\s\S]*?<\/style>/gi, "") // Remove style tags
          .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, "") // Remove script tags
          .replace(/<[^>]*>/g, " ") // Replace tags with spaces
          .replace(/\s+/g, " ") // Normalize whitespace
          .trim() || "";
    }
  }

  return hiddenContent;
}
