# PDF Processing Enhancements

## Overview

This document describes the enhanced PDF and CSV processing capabilities added to the `LocalFileAdapter` in the Garuda Intel pipeline.

## New Features

### 1. PDF Image Extraction

The PDF processor now automatically extracts embedded images from PDF files and saves them to a subdirectory for further processing.

#### How It Works

- When processing a PDF file, images are extracted from each page
- Images are saved to `{pdf_filename}_images/` directory alongside the PDF
- Each image is named `page{N}_img{M}.{ext}` where:
  - `N` is the page number (1-indexed)
  - `M` is the image index on that page (1-indexed)
  - `{ext}` is the image format extension (detected or defaults to .png)

#### Image Processing

For each extracted image:
- **Dimensions**: Width and height are detected (if PIL is available)
- **OCR**: Text extraction via Tesseract OCR (if pytesseract is available)
- **Metadata**: Stored in the document metadata including:
  - `extracted_images_dir`: Directory containing extracted images
  - `extracted_images_count`: Number of images extracted
  - `extracted_image_paths`: List of full paths to extracted images

#### Example Output

```
[Page 1]
Document text here...

[Embedded Image: page1_img1.png from Page 1 - 800x600]
Image OCR: Text found in the image

[PDF contains 5 embedded image(s)]
```

### 2. Table Data Extraction

The adapter now detects and extracts table-like data from both PDF and text content.

#### Supported Table Formats

1. **Pipe-delimited tables** (Markdown style):
   ```
   | Name | Age | City |
   | John | 25  | NYC  |
   | Jane | 30  | LA   |
   ```

2. **Tab-delimited tables**:
   ```
   Name    Age    City
   John    25     NYC
   Jane    30     LA
   ```

#### Structured Output

Tables are formatted into a structured representation:

```
Table (3 rows, 3 columns):
Headers: Name | Age | City
Row 1: Name: John | Age: 25 | City: NYC
Row 2: Name: Jane | Age: 30 | City: LA
```

This format makes it easier for LLMs to extract intelligence from tabular data.

### 3. Enhanced CSV Processing

CSV files now receive special structured data extraction in addition to raw content.

#### Features

- Raw CSV content is preserved for full context
- Structured key-value format is generated for better LLM processing
- Column headers are used as keys
- Each row is formatted with explicit column-value pairs

#### Example Output

```
Product,Price,Quantity
Widget,10.99,100
Gadget,25.50,50

[Structured Table Data]
CSV Table (2 data rows, 3 columns):
Columns: Product | Price | Quantity
Row 1: Product: Widget | Price: 10.99 | Quantity: 100
Row 2: Product: Gadget | Price: 25.50 | Quantity: 50
```

## New Methods

### `_extract_images_from_pdf_page(page, page_num, pdf_path)`

Extracts embedded images from a single PDF page.

**Parameters:**
- `page`: PyPDF2 page object
- `page_num`: Page number (0-indexed)
- `pdf_path`: Path to the source PDF file

**Returns:**
- List of dictionaries containing image information:
  - `filename`: Generated filename for the image
  - `path`: Full path where image was saved
  - `page_num`: Page number (1-indexed)
  - `source_pdf`: Path to source PDF
  - `width`: Image width in pixels (if available)
  - `height`: Image height in pixels (if available)
  - `ocr_text`: OCR-extracted text (if available)

### `_extract_tables_from_text(text)`

Extracts table-like data from text content.

**Parameters:**
- `text`: Text content that may contain tables

**Returns:**
- Structured text representation of all tables found, or empty string

**Detection Patterns:**
- Pipe-delimited tables (Markdown style)
- Tab-delimited data

### `_format_table_rows(rows)`

Formats table rows into a readable text representation.

**Parameters:**
- `rows`: List of row data, where each row is a list of cell values

**Returns:**
- Formatted table string with headers and structured row data

### `_extract_csv_structured(path, raw_content)`

Extracts structured data from CSV files.

**Parameters:**
- `path`: CSV file path (for context)
- `raw_content`: Raw CSV text content

**Returns:**
- Structured text representation of CSV data in key-value format

## Updated Methods

### `_extract_pdf_content(path)`

**Enhanced to:**
- Extract text from ALL pages (never skip failed pages)
- Extract embedded images from each page
- Apply table detection to extracted text
- Include image references in the output
- Track the number of extracted images

**New behavior:**
- Pages that fail text extraction show `[Text extraction failed]` instead of being skipped
- Image extraction failures don't halt PDF processing
- Table extraction failures don't halt PDF processing

### `_extract_text_content(path)`

**Enhanced to:**
- Detect CSV files and apply structured extraction
- Append structured table data to raw content for CSV files
- Maintain backward compatibility for non-CSV text files

### `_build_metadata(path, file_type)`

**Enhanced to:**
- Check for extracted images directory for PDF files
- Add metadata fields:
  - `extracted_images_dir`: Path to images directory
  - `extracted_images_count`: Number of extracted images
  - `extracted_image_paths`: List of image file paths

## Dependencies

These enhancements leverage existing optional dependencies:

- **PyPDF2**: Required for PDF processing (image extraction support)
- **Pillow (PIL)**: Optional, for image dimension detection
- **pytesseract**: Optional, for OCR on extracted images

## Error Handling

All new features are designed with graceful degradation:

- If PyPDF2 doesn't support image extraction, the feature is skipped
- If PIL is not available, image dimensions are shown as `?x?`
- If pytesseract is not available, OCR is skipped
- Individual image extraction failures don't stop PDF processing
- Table extraction failures don't stop content processing

## Use Cases

### Intelligence Extraction from Technical Documents

PDFs containing diagrams, charts, and tables can now have their embedded images extracted and OCR'd, providing richer content for intelligence gathering.

### Financial Reports

CSV and tabular data in PDFs are now structured for better LLM understanding, improving extraction of financial metrics and data points.

### Research Papers

Embedded figures and data tables are extracted and processed, allowing the intel pipeline to analyze both textual and visual content.

## Example Usage

```python
from garuda_intel.sources.local_file_adapter import LocalFileAdapter

# Initialize adapter
adapter = LocalFileAdapter()

# Process PDF with embedded images
documents = adapter.fetch("/path/to/document.pdf")

# The document content will include:
# - Extracted text from all pages
# - References to embedded images
# - OCR text from images (if available)
# - Structured table data (if tables are detected)

# Metadata will include paths to extracted images
metadata = documents[0].metadata
if "extracted_images_count" in metadata:
    print(f"Extracted {metadata['extracted_images_count']} images")
    print(f"Images saved to: {metadata['extracted_images_dir']}")
```

## Performance Considerations

- Image extraction adds processing time proportional to the number of images
- OCR on images can be slow for high-resolution images
- Directory creation is done only once per PDF
- Failed extractions are caught and logged without stopping processing

## Future Enhancements

Potential future improvements:

1. Support for image compression/resizing before saving
2. Advanced table detection using ML models
3. Support for additional table formats (space-aligned columns)
4. Image deduplication across pages
5. Metadata extraction from image EXIF data
6. Table extraction using specialized libraries (tabula-py, camelot)
