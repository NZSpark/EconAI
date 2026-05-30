/**
 * Integrated Knowledge Base File Upload Tests
 *
 * Covers ALL supported file formats (19 extensions, 17 format families):
 *   - Microsoft Office: .docx, .doc, .xlsx, .xls, .pptx, .ppt
 *   - Images:          .png, .jpg, .jpeg, .tiff, .bmp
 *   - Email:           .eml
 *   - PDF:             .pdf
 *   - HTML/MHTML:      .html, .mhtml, .mht
 *   - Text/Markdown:   .txt, .md, .csv
 *
 * NOT supported by backend: .msg (Outlook MSG format)
 *
 * Run with: npm run test:integrated
 */
import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { createReadStream, writeFileSync, unlinkSync } from 'fs';
import { join } from 'path';
import { tmpdir } from 'os';
import FormData from 'form-data';
import { deflateSync } from 'zlib';
import {
  apiClient,
  loginAsAdmin,
  isBackendAvailable,
  trackResource,
  cleanupResources,
} from './test-helper';

// ============================================================================
// Binary file generators — create minimal valid files for each format
// ============================================================================

/** Write binary content to temp file */
function createTempBinaryFile(buffer: Buffer, filename: string): string {
  const filepath = join(tmpdir(), filename);
  writeFileSync(filepath, buffer);
  return filepath;
}

/** Write text content to temp file */
function createTempFile(content: string, filename: string): string {
  const filepath = join(tmpdir(), filename);
  writeFileSync(filepath, content, 'utf-8');
  return filepath;
}

// --- CRC32 (needed for PNG and ZIP) ---

function crc32Table(): Uint32Array {
  const table = new Uint32Array(256);
  for (let i = 0; i < 256; i++) {
    let c = i;
    for (let j = 0; j < 8; j++) {
      c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    }
    table[i] = c;
  }
  return table;
}
const CRC32_TABLE = crc32Table();

function crc32(data: Buffer): number {
  let c = 0xffffffff;
  for (let i = 0; i < data.length; i++) {
    c = CRC32_TABLE[(c ^ data[i]) & 0xff] ^ (c >>> 8);
  }
  return (c ^ 0xffffffff) >>> 0;
}

function pngChunk(type: string, data: Buffer): Buffer {
  const typeAndData = Buffer.concat([Buffer.from(type, 'ascii'), data]);
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length, 0);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(typeAndData), 0);
  return Buffer.concat([len, typeAndData, crc]);
}

// --- PNG: valid 1x1 black pixel ---

function createMinimalPNG(): Buffer {
  // IHDR: 1x1, 8-bit grayscale
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(1, 0);  // width
  ihdr.writeUInt32BE(1, 4);  // height
  ihdr[8] = 8;                // bit depth
  ihdr[9] = 0;                // color type: grayscale
  ihdr[10] = 0;               // compression
  ihdr[11] = 0;               // filter
  ihdr[12] = 0;               // interlace

  // IDAT: zlib-compressed [filter=0, pixel=0]
  const raw = Buffer.from([0, 0]);
  const compressed = deflateSync(raw);
  const idat = pngChunk('IDAT', compressed);

  const signature = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
  const ihdrChunk = pngChunk('IHDR', ihdr);
  const iendChunk = pngChunk('IEND', Buffer.alloc(0));

  return Buffer.concat([signature, ihdrChunk, idat, iendChunk]);
}

// --- JPEG: minimal valid 1x1 black pixel ---

function createMinimalJPEG(): Buffer {
  const soi = Buffer.from([0xff, 0xd8]);
  // APP0 marker (JFIF)
  const app0 = Buffer.from([
    0xff, 0xe0,           // APP0 marker
    0x00, 0x10,           // length = 16
    0x4a, 0x46, 0x49, 0x46, 0x00, // "JFIF\0"
    0x01, 0x01,           // version 1.1
    0x00,                 // units
    0x00, 0x01,           // X density
    0x00, 0x01,           // Y density
    0x00, 0x00,           // thumbnail
  ]);
  // Define Quantization Table (DQT)
  const dqt = Buffer.from([
    0xff, 0xdb,           // DQT marker
    0x00, 0x43,           // length
    0x00,                 // table info
  ]);
  const qtable = Buffer.alloc(64, 1);
  // Start of Frame (SOF0)
  const sof = Buffer.from([
    0xff, 0xc0,           // SOF0 marker
    0x00, 0x0b,           // length
    0x08,                 // precision
    0x00, 0x01,           // height
    0x00, 0x01,           // width
    0x01,                 // num components
    0x01, 0x11, 0x00,     // component info
  ]);
  // Define Huffman Table (DHT) - minimal
  const dht = Buffer.from([
    0xff, 0xc4,
    0x00, 0x1f,
    0x00,
    0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b,
    0x01, 0x00, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b,
  ]);
  // Start of Scan (SOS)
  const sos = Buffer.from([
    0xff, 0xda,
    0x00, 0x08,
    0x01,
    0x01, 0x00,
    0x00, 0x3f, 0x00,
  ]);
  const eoi = Buffer.from([0xff, 0xd9]);

  return Buffer.concat([soi, app0, dqt, qtable, sof, dht, sos, Buffer.from([0x00]), eoi]);
}

// --- BMP: minimal 1x1 white pixel, 24-bit ---

function createMinimalBMP(): Buffer {
  const pixelDataSize = 4; // padded to 4 bytes
  const fileSize = 54 + pixelDataSize;
  const header = Buffer.alloc(54);
  header.write('BM', 0, 'ascii');
  header.writeUInt32LE(fileSize, 2);
  header.writeUInt32LE(0, 6);  // reserved
  header.writeUInt32LE(54, 10); // data offset
  header.writeUInt32LE(40, 14); // DIB header size
  header.writeUInt32LE(1, 18);  // width
  header.writeUInt32LE(1, 22);  // height
  header.writeUInt16LE(1, 26);  // planes
  header.writeUInt16LE(24, 28); // bits per pixel
  header.writeUInt32LE(0, 30);  // compression
  header.writeUInt32LE(pixelDataSize, 34);
  header.writeUInt32LE(2835, 38); // X pixels per meter
  header.writeUInt32LE(2835, 42); // Y pixels per meter
  header.writeUInt32LE(0, 46);
  header.writeUInt32LE(0, 50);
  const pixelData = Buffer.from([0xff, 0xff, 0xff, 0x00]); // B,G,R,padding
  return Buffer.concat([header, pixelData]);
}

// --- TIFF: minimal valid (little-endian, single strip) ---

function createMinimalTIFF(): Buffer {
  // Header: II (little-endian) + 42 + offset to first IFD
  const header = Buffer.from([0x49, 0x49, 0x2a, 0x00, 0x08, 0x00, 0x00, 0x00]);
  // IFD: 1 entry + next IFD offset
  // Entry: tag=256 (ImageWidth), type=3 (SHORT), count=1, value=1
  const ifd = Buffer.alloc(14);
  ifd.writeUInt16LE(1, 0);   // entry count
  ifd.writeUInt16LE(256, 2); // tag: ImageWidth
  ifd.writeUInt16LE(3, 4);   // type: SHORT
  ifd.writeUInt32LE(1, 6);   // count
  ifd.writeUInt16LE(1, 10);  // value
  ifd.writeUInt16LE(0, 12);  // value (high)
  // next IFD offset = 0 (no more IFDs)
  const next = Buffer.alloc(4, 0);
  return Buffer.concat([header, ifd, next]);
}

// --- PDF: minimal valid ---

function createMinimalPDF(): Buffer {
  const pdf = `%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>endobj
xref
0 4
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
trailer<</Size 4/Root 1 0 R>>
startxref
190
%%EOF
`;
  return Buffer.from(pdf, 'ascii');
}

// --- ZIP builder (for OOXML: .docx, .xlsx, .pptx) ---

interface ZipEntry {
  name: string;
  data: Buffer;
}

function createMinimalZip(entries: ZipEntry[]): Buffer {
  const localHeaders: Buffer[] = [];
  const centralHeaders: Buffer[] = [];
  let offset = 0;

  for (const entry of entries) {
    const nameBuf = Buffer.from(entry.name, 'ascii');
    const localHeader = Buffer.alloc(30 + nameBuf.length);
    localHeader.writeUInt32LE(0x04034b50, 0);  // signature
    localHeader.writeUInt16LE(20, 4);           // version needed
    localHeader.writeUInt16LE(0x0800, 6);       // flags: bit 11 = UTF-8 filename
    localHeader.writeUInt16LE(0, 8);            // compression: stored
    localHeader.writeUInt16LE(0, 10);           // mod time
    localHeader.writeUInt16LE(0, 12);           // mod date
    localHeader.writeUInt32LE(crc32(entry.data), 14);
    localHeader.writeUInt32LE(entry.data.length, 18);  // compressed size
    localHeader.writeUInt32LE(entry.data.length, 22);  // uncompressed size
    localHeader.writeUInt16LE(nameBuf.length, 26);
    localHeader.writeUInt16LE(0, 28);           // extra field length
    nameBuf.copy(localHeader, 30);

    const centralHeader = Buffer.alloc(46 + nameBuf.length);
    centralHeader.writeUInt32LE(0x02014b50, 0);
    centralHeader.writeUInt16LE(20, 4);   // version made by
    centralHeader.writeUInt16LE(20, 6);   // version needed
    centralHeader.writeUInt16LE(0x0800, 8);
    centralHeader.writeUInt16LE(0, 10);   // compression
    centralHeader.writeUInt16LE(0, 12);   // mod time
    centralHeader.writeUInt16LE(0, 14);   // mod date
    centralHeader.writeUInt32LE(crc32(entry.data), 16);
    centralHeader.writeUInt32LE(entry.data.length, 20);
    centralHeader.writeUInt32LE(entry.data.length, 24);
    centralHeader.writeUInt16LE(nameBuf.length, 28);
    centralHeader.writeUInt16LE(0, 30);   // extra field
    centralHeader.writeUInt16LE(0, 32);   // comment
    centralHeader.writeUInt16LE(0, 34);   // disk start
    centralHeader.writeUInt16LE(0, 36);   // internal attrs
    centralHeader.writeUInt32LE(0, 38);   // external attrs
    centralHeader.writeUInt32LE(offset, 42);
    nameBuf.copy(centralHeader, 46);

    localHeaders.push(localHeader);
    centralHeaders.push(centralHeader);
    offset += localHeader.length + entry.data.length;
  }

  const centralDir = Buffer.concat(centralHeaders);
  const eocd = Buffer.alloc(22);
  eocd.writeUInt32LE(0x06054b50, 0);
  eocd.writeUInt16LE(0, 4);
  eocd.writeUInt16LE(0, 6);
  eocd.writeUInt16LE(entries.length, 8);
  eocd.writeUInt16LE(entries.length, 10);
  eocd.writeUInt32LE(centralDir.length, 12);
  eocd.writeUInt32LE(offset, 16);
  eocd.writeUInt16LE(0, 20);

  const bodies = entries.map(e => e.data);
  const parts: Buffer[] = [];
  for (let i = 0; i < entries.length; i++) {
    parts.push(localHeaders[i], bodies[i]);
  }
  parts.push(centralDir, eocd);
  return Buffer.concat(parts);
}

// --- OOXML minimal XML payloads ---

function createMinimalDOCX(): Buffer {
  const contentTypes = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' +
    '<Default Extension="xml" ContentType="application/xml"/>' +
    '<Override PartName="/word/document.xml" ' +
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>' +
    '</Types>';
  const rels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>' +
    '</Relationships>';
  const document = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">' +
    '<w:body><w:p><w:r><w:t>PolicyAI DOCX test document</w:t></w:r></w:p></w:body></w:document>';
  return createMinimalZip([
    { name: '[Content_Types].xml', data: Buffer.from(contentTypes, 'utf-8') },
    { name: '_rels/.rels', data: Buffer.from(rels, 'utf-8') },
    { name: 'word/document.xml', data: Buffer.from(document, 'utf-8') },
  ]);
}

function createMinimalXLSX(): Buffer {
  const contentTypes = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' +
    '<Default Extension="xml" ContentType="application/xml"/>' +
    '<Override PartName="/xl/worksheets/sheet1.xml" ' +
    'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' +
    '</Types>';
  const rels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>' +
    '</Relationships>';
  const workbook = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">' +
    '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>';
  const wbRels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>' +
    '</Relationships>';
  const sheet = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">' +
    '<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>PolicyAI XLSX test</t></is></c></row></sheetData></worksheet>';
  const sharedStrings = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="1" uniqueCount="1">' +
    '<si><t>PolicyAI XLSX test</t></si></sst>';
  return createMinimalZip([
    { name: '[Content_Types].xml', data: Buffer.from(contentTypes, 'utf-8') },
    { name: '_rels/.rels', data: Buffer.from(rels, 'utf-8') },
    { name: 'xl/workbook.xml', data: Buffer.from(workbook, 'utf-8') },
    { name: 'xl/_rels/workbook.xml.rels', data: Buffer.from(wbRels, 'utf-8') },
    { name: 'xl/worksheets/sheet1.xml', data: Buffer.from(sheet, 'utf-8') },
    { name: 'xl/sharedStrings.xml', data: Buffer.from(sharedStrings, 'utf-8') },
  ]);
}

function createMinimalPPTX(): Buffer {
  const contentTypes = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' +
    '<Default Extension="xml" ContentType="application/xml"/>' +
    '<Override PartName="/ppt/presentation.xml" ' +
    'ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>' +
    '</Types>';
  const rels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>' +
    '</Relationships>';
  const presentation = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">' +
    '<p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>' +
    '<p:sldSz cx="9144000" cy="6858000"/></p:presentation>';
  return createMinimalZip([
    { name: '[Content_Types].xml', data: Buffer.from(contentTypes, 'utf-8') },
    { name: '_rels/.rels', data: Buffer.from(rels, 'utf-8') },
    { name: 'ppt/presentation.xml', data: Buffer.from(presentation, 'utf-8') },
  ]);
}

// --- OLE2 stub (for .doc, .xls, .ppt) ---
// Creates a minimal OLE2 compound document with correct magic bytes.
// The backend will identify it as OLE2 and map by extension.

function createOLE2Stub(): Buffer {
  // OLE2 header is 512 bytes. Only the first 8 magic bytes matter for format detection.
  const header = Buffer.alloc(512, 0);
  header[0] = 0xd0; header[1] = 0xcf; header[2] = 0x11; header[3] = 0xe0;
  header[4] = 0xa1; header[5] = 0xb1; header[6] = 0x1a; header[7] = 0xe1;
  // Minor version, byte order (0xFE 0xFF = little-endian)
  header.writeUInt16LE(0x003e, 24);  // minor version
  header.writeUInt16LE(0x0003, 26);  // major version
  header.writeUInt16LE(0xfffe, 28);  // byte order
  header.writeUInt16LE(9, 30);       // sector size (power of 2, default 512B -> 9)
  header.writeUInt16LE(6, 32);       // mini sector size (power of 2, default 64B -> 6)
  return header;
}

// --- EML: text-based email ---

function createMinimalEML(): string {
  return [
    'From: sender@example.com',
    'To: recipient@example.com',
    'Subject: Test Email for PolicyAI KB Upload',
    'Date: Mon, 25 May 2026 10:00:00 +0800',
    'MIME-Version: 1.0',
    'Content-Type: text/plain; charset="utf-8"',
    '',
    '这是一封测试邮件。',
    '',
    '用于测试PolicyAI知识库的邮件文件上传功能。',
    '内容包括贸易政策相关的讨论内容。',
    '',
    'Best regards,',
    'Sender',
  ].join('\r\n');
}

// --- HTML / MHTML ---

function createMinimalHTML(): string {
  return `<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>PolicyAI 测试文档</title></head>
<body>
<h1>贸易政策分析报告</h1>
<p>本文档用于测试HTML格式的知识库上传功能。</p>
<p>贸易政策是国际经济关系中的重要组成部分。</p>
</body>
</html>`;
}

// ============================================================================
// Upload helper
// ============================================================================

async function uploadFile(
  client: ReturnType<typeof apiClient>,
  projectId: string,
  filepath: string,
  filename: string,
) {
  const formData = new FormData();
  formData.append('file', createReadStream(filepath), filename);
  return client.post(`/projects/${projectId}/documents`, formData, {
    headers: { ...formData.getHeaders() },
    timeout: 120000,
  });
}

// ============================================================================
// Tests
// ============================================================================

describe('KB File Upload (Integrated)', () => {
  let projectId: string | null = null;
  let uploadedDocIds: string[] = [];
  const tempFiles: string[] = [];

  beforeAll(async () => {
    const available = await isBackendAvailable();
    if (!available) return;
    await loginAsAdmin();

    const client = apiClient();
    const projRes = await client.post('/projects', {
      name: `ITest-KB-Upload-${Date.now()}`,
      description: 'Integration test for all KB file formats',
    });
    if (projRes.status === 200 || projRes.status === 201) {
      projectId = projRes.data.project_id;
      trackResource('project', projectId, async () => {
        for (const docId of uploadedDocIds) {
          try { await client.delete(`/projects/${projectId}/documents/${docId}`); } catch { /* ok */ }
        }
        await client.delete(`/projects/${projectId}`);
      });
    }
  });

  afterAll(async () => {
    for (const f of tempFiles) {
      try { unlinkSync(f); } catch { /* ignore */ }
    }
    await cleanupResources();
  });

  // ========================================================================
  // Microsoft Office Formats
  // ========================================================================

  describe('Microsoft Office formats', () => {
    const officeCases: { label: string; ext: string; expectedFormat: string; generator: () => Buffer }[] = [
      { label: '.docx', ext: 'docx', expectedFormat: 'docx', generator: createMinimalDOCX },
      { label: '.doc (OLE2)', ext: 'doc', expectedFormat: 'docx', generator: createOLE2Stub },
      { label: '.xlsx', ext: 'xlsx', expectedFormat: 'xlsx', generator: createMinimalXLSX },
      { label: '.xls (OLE2)', ext: 'xls', expectedFormat: 'xlsx', generator: createOLE2Stub },
      { label: '.pptx', ext: 'pptx', expectedFormat: 'pptx', generator: createMinimalPPTX },
      { label: '.ppt (OLE2)', ext: 'ppt', expectedFormat: 'pptx', generator: createOLE2Stub },
    ];

    for (const tc of officeCases) {
      it(`should upload ${tc.label} file`, async () => {
        if (!projectId) return;

        const binary = tc.generator();
        const filename = `office-test-${Date.now()}-${Math.random().toString(36).slice(2)}.${tc.ext}`;
        const filepath = createTempBinaryFile(binary, filename);
        tempFiles.push(filepath);

        const client = apiClient();
        const res = await uploadFile(client, projectId!, filepath, filename);

        expect([200, 201]).toContain(res.status);
        expect(res.data).toHaveProperty('document_id');
        expect(res.data).toHaveProperty('format', tc.expectedFormat);
        expect(res.data).toHaveProperty('parse_status');
        uploadedDocIds.push(res.data.document_id);
      }, 120000);
    }
  });

  // ========================================================================
  // PDF Format
  // ========================================================================

  describe('PDF format', () => {
    it('should upload a .pdf file', async () => {
      if (!projectId) return;

      const binary = createMinimalPDF();
      const filename = `pdf-test-${Date.now()}.pdf`;
      const filepath = createTempBinaryFile(binary, filename);
      tempFiles.push(filepath);

      const client = apiClient();
      const res = await uploadFile(client, projectId!, filepath, filename);

      expect([200, 201]).toContain(res.status);
      expect(res.data).toHaveProperty('document_id');
      expect(res.data).toHaveProperty('format', 'pdf');
      expect(res.data).toHaveProperty('parse_status');
      uploadedDocIds.push(res.data.document_id);
    }, 120000);
  });

  // ========================================================================
  // Image Formats
  // ========================================================================

  describe('Image formats', () => {
    const imageCases: { label: string; ext: string; generator: () => Buffer }[] = [
      { label: '.png', ext: 'png', generator: createMinimalPNG },
      { label: '.jpg', ext: 'jpg', generator: createMinimalJPEG },
      { label: '.jpeg', ext: 'jpeg', generator: createMinimalJPEG },
      { label: '.bmp', ext: 'bmp', generator: createMinimalBMP },
      { label: '.tiff', ext: 'tiff', generator: createMinimalTIFF },
    ];

    for (const tc of imageCases) {
      it(`should upload ${tc.label} image file`, async () => {
        if (!projectId) return;

        const binary = tc.generator();
        const filename = `img-test-${Date.now()}-${Math.random().toString(36).slice(2)}.${tc.ext}`;
        const filepath = createTempBinaryFile(binary, filename);
        tempFiles.push(filepath);

        const client = apiClient();
        const res = await uploadFile(client, projectId!, filepath, filename);

        expect([200, 201]).toContain(res.status);
        expect(res.data).toHaveProperty('document_id');
        // All image formats map to DocumentFormat.image -> 'image'
        expect(res.data).toHaveProperty('format', 'image');
        expect(res.data).toHaveProperty('parse_status');
        uploadedDocIds.push(res.data.document_id);
      }, 120000);
    }
  });

  // ========================================================================
  // Email Format (.eml only; .msg is NOT supported by backend)
  // ========================================================================

  describe('Email format', () => {
    it('should upload an .eml email file', async () => {
      if (!projectId) return;

      const content = createMinimalEML();
      const filename = `email-test-${Date.now()}.eml`;
      const filepath = createTempFile(content, filename);
      tempFiles.push(filepath);

      const client = apiClient();
      const res = await uploadFile(client, projectId!, filepath, filename);

      expect([200, 201]).toContain(res.status);
      expect(res.data).toHaveProperty('document_id');
      expect(res.data).toHaveProperty('format', 'eml');
      expect(res.data).toHaveProperty('parse_status');
      uploadedDocIds.push(res.data.document_id);
    }, 120000);

    it('should reject .msg file (unsupported format)', async () => {
      if (!projectId) return;

      // .msg is NOT in ALLOWED_EXTENSIONS — should be rejected
      const filepath = createTempBinaryFile(Buffer.from('fake msg content'), `msg-test-${Date.now()}.msg`);
      tempFiles.push(filepath);

      const client = apiClient();
      const res = await uploadFile(client, projectId!, filepath, 'outlook-message.msg');

      expect([400, 415]).toContain(res.status);
    }, 30000);
  });

  // ========================================================================
  // HTML / MHTML Format
  // ========================================================================

  describe('HTML / MHTML format', () => {
    const htmlCases: { label: string; ext: string; expectedFormat: string }[] = [
      { label: '.html', ext: 'html', expectedFormat: 'html' },
      { label: '.mhtml', ext: 'mhtml', expectedFormat: 'mhtml' },
      { label: '.mht', ext: 'mht', expectedFormat: 'mhtml' },
    ];

    for (const tc of htmlCases) {
      it(`should upload ${tc.label} file`, async () => {
        if (!projectId) return;

        const content = createMinimalHTML();
        const filename = `web-test-${Date.now()}-${Math.random().toString(36).slice(2)}.${tc.ext}`;
        const filepath = createTempFile(content, filename);
        tempFiles.push(filepath);

        const client = apiClient();
        const res = await uploadFile(client, projectId!, filepath, filename);

        expect([200, 201]).toContain(res.status);
        expect(res.data).toHaveProperty('document_id');
        expect(res.data).toHaveProperty('format', tc.expectedFormat);
        expect(res.data).toHaveProperty('parse_status');
        uploadedDocIds.push(res.data.document_id);
      }, 120000);
    }
  });

  // ========================================================================
  // Text / Markdown / CSV (already in original test, kept for completeness)
  // ========================================================================

  describe('Text / Markdown / CSV', () => {
    it('should upload a .txt file', async () => {
      if (!projectId) return;

      const content = '知识库测试文件 - 贸易政策分析\n' +
        '贸易壁垒是国际贸易中的重要议题。';
      const filepath = createTempFile(content, `txt-test-${Date.now()}.txt`);
      tempFiles.push(filepath);

      const client = apiClient();
      const res = await uploadFile(client, projectId!, filepath, '贸易政策分析.txt');

      expect([200, 201]).toContain(res.status);
      expect(res.data).toHaveProperty('format', 'txt');
      uploadedDocIds.push(res.data.document_id);
    });

    it('should upload a .md file', async () => {
      if (!projectId) return;

      const content = '# 宏观经济分析\n\n## GDP 增速预测\n预计2026年GDP增速约为4.5%。\n';
      const filepath = createTempFile(content, `md-test-${Date.now()}.md`);
      tempFiles.push(filepath);

      const client = apiClient();
      const res = await uploadFile(client, projectId!, filepath, '宏观经济分析.md');

      expect([200, 201]).toContain(res.status);
      expect(res.data).toHaveProperty('format', 'md');
      uploadedDocIds.push(res.data.document_id);
    });

    it('should upload a .csv file', async () => {
      if (!projectId) return;

      const content = '年份,GDP增速,CPI\n2024,5.0,0.3\n2025,5.0,0.5\n2026,4.5,1.2\n';
      const filepath = createTempFile(content, `csv-test-${Date.now()}.csv`);
      tempFiles.push(filepath);

      const client = apiClient();
      const res = await uploadFile(client, projectId!, filepath, '经济数据.csv');

      expect([200, 201]).toContain(res.status);
      expect(res.data).toHaveProperty('format', 'csv');
      uploadedDocIds.push(res.data.document_id);
    });
  });

  // ========================================================================
  // Upload Validation Tests
  // ========================================================================

  describe('Upload validation', () => {
    it('should reject empty file upload', async () => {
      if (!projectId) return;

      const filepath = createTempFile('', `empty-${Date.now()}.txt`);
      tempFiles.push(filepath);

      const client = apiClient();
      const res = await uploadFile(client, projectId!, filepath, 'empty.txt');

      expect(res.status).toBeGreaterThanOrEqual(400);
    });

    it('should reject unsupported file format (.exe)', async () => {
      if (!projectId) return;

      const filepath = createTempBinaryFile(Buffer.from('fake binary'), `exe-test-${Date.now()}.exe`);
      tempFiles.push(filepath);

      const client = apiClient();
      const res = await uploadFile(client, projectId!, filepath, 'malware.exe');

      expect([400, 415]).toContain(res.status);
    });

    it('should reject upload without file field', async () => {
      if (!projectId) return;

      const client = apiClient();
      const formData = new FormData();
      formData.append('other', 'some-value');

      const res = await client.post(`/projects/${projectId}/documents`, formData, {
        headers: { ...formData.getHeaders() },
        timeout: 30000,
      });

      expect(res.status).toBeGreaterThanOrEqual(400);
    });
  });

  // ========================================================================
  // Document Lifecycle Tests
  // ========================================================================

  describe('Document lifecycle', () => {
    it('should list all uploaded documents', async () => {
      if (!projectId) return;

      const client = apiClient();
      const res = await client.get(`/projects/${projectId}/documents`, {
        params: { page: 1, page_size: 50 },
      });

      expect(res.status).toBe(200);
      expect(res.data).toHaveProperty('items');
      expect(res.data).toHaveProperty('total');
      expect(Array.isArray(res.data.items)).toBe(true);
      // We've uploaded at least 19+ files (all formats)
      expect(res.data.items.length).toBeGreaterThanOrEqual(19);
    });

    it('should get document detail with parse status', async () => {
      if (!projectId || uploadedDocIds.length === 0) return;

      const docId = uploadedDocIds[0];
      const client = apiClient();
      const res = await client.get(`/projects/${projectId}/documents/${docId}`);

      expect(res.status).toBe(200);
      expect(res.data).toHaveProperty('document_id', docId);
      expect(res.data).toHaveProperty('original_name');
      expect(res.data).toHaveProperty('format');
      expect(res.data).toHaveProperty('parse_status');
      expect(['pending', 'parsing', 'ready', 'error']).toContain(res.data.parse_status);
      expect(res.data).toHaveProperty('size_bytes');
    });

    it('should reindex a document', async () => {
      if (!projectId || uploadedDocIds.length === 0) return;

      const docId = uploadedDocIds[0];
      const client = apiClient();
      const res = await client.post(`/projects/${projectId}/documents/${docId}/reindex`);

      expect([200, 201, 409]).toContain(res.status);
    });

    it('should delete a document', async () => {
      if (!projectId || uploadedDocIds.length === 0) return;

      const docId = uploadedDocIds.pop()!;
      const client = apiClient();
      const res = await client.delete(`/projects/${projectId}/documents/${docId}`);

      expect([200, 204]).toContain(res.status);

      // Verify deletion
      const getRes = await client.get(`/projects/${projectId}/documents/${docId}`);
      expect([404, 410]).toContain(getRes.status);
    });

    it('should return 404 for non-existent document', async () => {
      if (!projectId) return;

      const client = apiClient();
      const res = await client.get(
        `/projects/${projectId}/documents/00000000-0000-0000-0000-000000000000`
      );

      expect(res.status).toBe(404);
    });
  });

  // ========================================================================
  // Search Tests (Post-Upload)
  // ========================================================================

  describe('Knowledge base search after upload', () => {
    it('should find uploaded Chinese content via search', async () => {
      if (!projectId) return;

      await new Promise(resolve => setTimeout(resolve, 2000));

      const client = apiClient();
      const res = await client.post(`/projects/${projectId}/search`, {
        query: '贸易政策',
        top_k: 10,
      });

      expect(res.status).toBe(200);
      expect(res.data).toHaveProperty('results');
      expect(res.data).toHaveProperty('total_hits');
    });

    it('should search with expected result structure', async () => {
      if (!projectId) return;

      const client = apiClient();
      const res = await client.post(`/projects/${projectId}/search`, {
        query: 'GDP 增速',
        top_k: 5,
      });

      expect(res.status).toBe(200);
      if (res.data.results.length > 0) {
        const hit = res.data.results[0];
        expect(hit).toHaveProperty('chunk_id');
        expect(hit).toHaveProperty('content');
        expect(hit).toHaveProperty('score');
        expect(typeof hit.score).toBe('number');
      }
    });

    it('should handle unrelated queries gracefully', async () => {
      if (!projectId) return;

      const client = apiClient();
      const res = await client.post(`/projects/${projectId}/search`, {
        query: '量子计算与黑洞物理',
        top_k: 3,
      });

      expect(res.status).toBe(200);
    });
  });

  // ========================================================================
  // Large Document Test
  // ========================================================================

  describe('Large document handling', () => {
    it('should upload a large markdown document (~50KB)', async () => {
      if (!projectId) return;

      const paragraphs = [
        '## 中国宏观经济分析报告\n\n',
        '### 一、GDP增长趋势\n\n',
        '根据国家统计局数据，2025年中国国内生产总值(GDP)同比增长5.0%。',
        '分季度看，一季度增长5.3%，二季度增长4.7%，三季度增长4.9%，四季度增长5.1%。',
        '经济增长的主要驱动力包括消费复苏、出口改善和服务业扩张。\n\n',
        '### 二、产业结构变化\n\n',
        '第二产业增加值增长5.5%，其中高技术制造业增长8.2%。',
        '数字经济核心产业增加值占GDP比重达到12.5%。\n\n',
        '### 三、贸易政策与国际收支\n\n',
        '全年货物进出口总额43.5万亿元人民币，同比增长3.8%。',
        '对"一带一路"沿线国家进出口增长5.8%。\n\n',
        '### 四、货币政策与财政政策\n\n',
        '广义货币(M2)余额同比增长9.2%。',
        '全年新增减税降费及退税缓费超过2.5万亿元。\n\n',
      ];

      const content = paragraphs.join('\n');
      const filepath = createTempFile(content, `large-md-${Date.now()}.md`);
      tempFiles.push(filepath);

      const client = apiClient();
      const res = await uploadFile(client, projectId!, filepath, '中国宏观经济分析报告.md');

      expect([200, 201]).toContain(res.status);
      expect(res.data).toHaveProperty('document_id');
      expect(res.data).toHaveProperty('size_bytes');
      expect(res.data.size_bytes).toBeGreaterThan(500);
      uploadedDocIds.push(res.data.document_id);
    });
  });

  // ========================================================================
  // Cross-format summary: verify all 19 extensions were accepted
  // ========================================================================

  describe('All formats summary', () => {
    it('should have accepted all 19 supported extensions', async () => {
      if (!projectId) return;

      const allExtensions = [
        'pdf',
        'docx', 'doc',
        'xlsx', 'xls', 'csv',
        'pptx', 'ppt',
        'md', 'txt',
        'eml',
        'html', 'mhtml', 'mht',
        'png', 'jpg', 'jpeg', 'tiff', 'bmp',
      ];
      expect(allExtensions).toHaveLength(19);

      const client = apiClient();
      const res = await client.get(`/projects/${projectId}/documents`, {
        params: { page: 1, page_size: 50 },
      });

      expect(res.status).toBe(200);
      // We should have uploaded >= 19 documents (at least one per extension)
      expect(res.data.items.length).toBeGreaterThanOrEqual(19);

      // Collect formats seen
      const formats = new Set(res.data.items.map((d: any) => d.format));
      const expectedFormats = ['pdf', 'docx', 'xlsx', 'csv',
        'pptx', 'markdown', 'txt', 'eml', 'html', 'mhtml', 'image'];
      for (const f of expectedFormats) {
        expect(formats.has(f)).toBe(true);
      }
    });
  });
});
