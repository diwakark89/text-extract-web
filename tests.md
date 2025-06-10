# Testing Scenarios for Hidden Text Extraction

## Overview
This document outlines test scenarios for the Text Extractor extension's ability to handle hidden content.

## Test Scenarios

### 1. Basic Hidden Elements
Test the extension with pages that have elements with `display: none` CSS property.

Example HTML to test with:
```html
<div class="container">
  <div class="visible-content">This is visible text</div>
  <div class="hidden-content" style="display: none">This is hidden text that should be extracted</div>
</div>
```

### 2. Reveal Button Interaction
Test pages with buttons that reveal hidden content when clicked.

Example HTML:
```html
<div class="question-container">
  <div class="question">What is the capital of France?</div>
  <button class="show-answer">Show Answer</button>
  <div class="answer" style="display: none">Paris</div>
</div>
```

### 3. Nested Hidden Content
Test with nested hidden elements to ensure all levels are extracted.

### 4. Dynamic Content Loading
Test with pages that load content dynamically after clicking a button.

### 5. Collapsed Accordions
Test with accordion UI patterns that hide/show content.

## Expected Results

When testing with "Include hidden text" option checked:
- All text content should be extracted, including hidden elements
- Content may include text from hidden elements based on CSS properties

## Troubleshooting

If hidden text is still not being extracted:
1. Check if the hidden content uses techniques other than `display: none` (e.g., visibility, opacity)
2. Verify the correct selector is being used
3. Check if content is loaded dynamically after page load
4. Some sites may use complex JavaScript to manage content visibility
