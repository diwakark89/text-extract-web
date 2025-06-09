/**
 * Content script for Question Text Extractor extension
 *
 * This script is injected into web pages to extract text from specified elements
 * using CSS selectors. It communicates with the popup via Chrome's messaging API.
 */

// Listen for messages from the popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
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

    // Get examName, tagList, prompt, text-to-remove values, and selectors-to-remove if provided
    console.log('Request from popup:', request);
    const examName = request.examName || "";
    const tagList = request.tagList || [];
    const prompt = request.prompt || "";
    const textToRemoveValues = request.textToRemoveValues || [];
    const selectorsToRemove = request.selectorsToRemove || [];

    console.log('Extracted parameters:', {
      examName,
      tagList,
      prompt,
      textToRemoveValues,
      selectorsToRemove
    });

    // Extract text based on provided selectors and options
    extractTextFromSelectors(request.selectors, { includeHiddenText, examName, tagList, prompt, textToRemoveValues, selectorsToRemove })
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
 * @param {string} options.examName - Exam name to include with the extracted text
 * @param {string[]} options.tagList - Array of tags to include with the extracted text
 * @param {string} options.prompt - Prompt text to include with the extracted text
 * @param {string[]} options.textToRemoveValues - Array of text patterns to remove from the extracted content
 * @returns {Promise<string>} - Promise resolving to formatted extracted text
 */
async function extractTextFromSelectors(
  selectors,
    options = { includeHiddenText: true, examName: "", tagList: [], prompt: "", textToRemoveValues: [], selectorsToRemove: [] }
) {
  try {
    let allExtractedText = [];

    // First, if selectors-to-remove are specified, get their content to exclude later
    let contentToRemove = [];
    if (options.selectorsToRemove && options.selectorsToRemove.length > 0) {
      for (const selectorToRemove of options.selectorsToRemove) {
        if (!selectorToRemove) continue;

        try {
          const elementsToRemove = document.querySelectorAll(selectorToRemove);
          if (elementsToRemove && elementsToRemove.length > 0) {
            // Extract text from each element that should be removed
            const textsFromSelector = Array.from(elementsToRemove)
              .map(el => {
                const visibleText = el.innerText.trim();
                const hiddenText = extractHiddenText(el);
                return visibleText || hiddenText || "";
              })
              .filter(text => text.length > 0);

            // Add all texts from this selector to the master list
            contentToRemove = [...contentToRemove, ...textsFromSelector];
          }
        } catch (error) {
          console.error(`Error processing selector-to-remove ${selectorToRemove}:`, error);
        }
      }
    }

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

    // First remove content from selector-to-remove if specified
    if (contentToRemove && contentToRemove.length > 0) {
      contentToRemove.forEach(content => {
        if (content) {
          try {
            // Escape special regex characters to treat the content as literal text
            const safePattern = content.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
            extractedText = extractedText.replace(new RegExp(safePattern, 'g'), '');
          } catch (e) {
            console.error('Error removing content:', e);
            // Fallback to simple string replacement if regex fails
            extractedText = extractedText.split(content).join('');
          }
        }
      });
    }

    // Then process text-to-remove patterns
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

    // Create response object with the new structure
    const responseObject = {
      prompt: options.prompt || "",
      examName: options.examName || "",
      mcqTextList: mcqTextArray,
      unwantedTexts: options.textToRemoveValues || [],
      tagList: options.tagList || [],
      userId: 2,            // Hardcoded as specified
      isPublic: true,       // Hardcoded as specified
      difficultyLevel: "EASY" // Hardcoded as specified
    };

    // Convert to JSON string with formatting
    const jsonString = JSON.stringify(responseObject, null, 2);
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
