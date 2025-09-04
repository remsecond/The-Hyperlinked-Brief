/**
 * Save Gmail threads matching queries as PDFs to a Drive folder.
 * Evidentiary features:
 *  - Full-thread preservation
 *  - Per-message headers incl. Message-ID + UTC timestamp
 *  - Durable CSV acquisition log in Drive
 *  - De-dup across queries + idempotent across runs (threadId memory)
 *  - Optional attachment capture per thread
 *  - Safe deterministic filenames with short threadId suffix
 *  - Render modes: "TEXT" (via Doc) or "HTML" (via HtmlService)
 */

/*** ==== CONFIG ==== ***/
const DRIVE_FOLDER_ID = 'YOUR_DRIVE_FOLDER_ID_HERE';            // <-- set this
const QUERIES = [
  // paste Precise / Intermediate / Broad queries here
];

const MAX_PER_QUERY = 5000;
const PAGE_SIZE     = 100;
const SLEEP_MS      = 250;
const RENDER_MODE   = 'TEXT';  // 'TEXT' or 'HTML'
const SAVE_ATTACHMENTS = true; // also save attachments per thread
const LOG_FILE_PREFIX  = 'acquisition_log_'; // new log per run
const ATTACH_SUBFOLDER_SUFFIX = '_attachments';

/*** ==== ENTRY ==== ***/
function exportEmailsToPDF() {
  const folder = DriveApp.getFolderById(DRIVE_FOLDER_ID);
  const processedAcrossQueries = new Set(); // dedupe across queries

  // Idempotency across runs via Properties
  const props = PropertiesService.getUserProperties();

  const logRows = [
    ["query","threadId","filename","fileId","fileUrl","messageCount","attachmentsCount","exportTimestampUTC","status","error"]
  ];

  QUERIES.forEach((q, qi) => {
    Logger.log(`Query ${qi+1}/${QUERIES.length}: ${q}`);
    const threadIds = fetchAllThreadIds(q);
    Logger.log(` -> Found ${threadIds.length} thread IDs`);
    threadIds.forEach((tid, i) => {
      if (processedAcrossQueries.has(tid)) return; // de-dup across queries
      processedAcrossQueries.add(tid);

      const alreadyDone = props.getProperty(keyFor(tid)) === '1';
      try {
        const th = GmailApp.getThreadById(tid);
        if (!th) return;

        const msgs = th.getMessages();
        if (!msgs || !msgs.length) return;

        // Build base filename from first message
        const first = msgs[0];
        const dateISO = Utilities.formatDate(first.getDate(), Session.getScriptTimeZone(), 'yyyy-MM-dd');
        const subj5   = takeFirstNWords(first.getSubject() || 'No Subject', 5);
        const fromShort = pickPrimaryNameOrEmail(first.getFrom());
        const toShort   = pickPrimaryNameOrEmail(first.getTo());
        const tidShort  = String(tid).slice(-8);

        const baseName = `[${dateISO}]_[${subj5}]_[${fromShort}]_[${toShort}]`;
        const filename = `${baseName}__TID_${tidShort}.pdf`;
        const safeFilename = sanitizeFilename(filename);

        // Idempotent by threadId memory OR pre-existing file
        if (alreadyDone || fileExistsInFolder(folder, safeFilename)) {
          logRows.push([q, tid, safeFilename, "", "", msgs.length, "", nowUTC(), "SKIP_EXISTS", ""]);
          props.setProperty(keyFor(tid), '1');
          return;
        }

        // Render thread
        let pdfBlob;
        if (RENDER_MODE === 'HTML') {
          const html = buildHtmlThread(msgs);
          pdfBlob = htmlToPdf(html, safeFilename);
        } else {
          const text = buildPlainTextThread(msgs);
          pdfBlob = textToPdfViaDoc(text, safeFilename);
        }

        const file = folder.createFile(pdfBlob).setName(safeFilename);

        // Attachments (optional)
        let attachCount = 0;
        if (SAVE_ATTACHMENTS) {
          const attachFolder = getOrCreateSubfolder(folder, baseName + ATTACH_SUBFOLDER_SUFFIX);
          msgs.forEach((m) => {
            const atts = m.getAttachments({includeInlineImages: true, includeAttachments: true}) || [];
            atts.forEach((a, idx) => {
              const attName = sanitizeFilename(`${baseName}__msg_${hashSafe(m.getHeader('Message-ID') || m.getId())}__att_${idx+1}__${a.getName()}`);
              attachFolder.createFile(a.copyBlob().setName(attName));
              attachCount++;
            });
          });
        }

        logRows.push([q, tid, safeFilename, file.getId(), file.getUrl(), msgs.length, attachCount, nowUTC(), "EXPORTED", ""]);
        props.setProperty(keyFor(tid), '1');
        Utilities.sleep(SLEEP_MS);
      } catch (e) {
        logRows.push([q, tid, "", "", "", "", "", nowUTC(), "ERROR", (e && e.message) || String(e)]);
      }
    });
  });

  // persist log to Drive (new file per run)
  const csvBlob = Utilities.newBlob(toCSV(logRows), "text/csv", `${LOG_FILE_PREFIX}${timestampSafe()}.csv`);
  DriveApp.getFolderById(DRIVE_FOLDER_ID).createFile(csvBlob);
  Logger.log('Done.');
}

/*** ==== HELPERS ==== ***/
function fetchAllThreadIds(query) {
  const ids = [];
  let start = 0;
  while (start < MAX_PER_QUERY) {
    const batch = GmailApp.search(query, start, PAGE_SIZE);
    if (!batch.length) break;
    batch.forEach(t => ids.push(t.getId()));
    start += batch.length;
    if (batch.length < PAGE_SIZE) break;
    Utilities.sleep(SLEEP_MS);
  }
  return ids;
}

function fileExistsInFolder(folder, name) {
  const it = folder.getFilesByName(name);
  return it.hasNext();
}
function getOrCreateSubfolder(folder, name) {
  let it = folder.getFoldersByName(name);
  if (it.hasNext()) return it.next();
  return folder.createFolder(name);
}
function pickPrimaryNameOrEmail(raw) {
  if (!raw) return 'Unknown';
  const firstPart = raw.split(',')[0].trim();
  const m = firstPart.match(/^"?(.*?)"?\s*<(.+?)>$/);
  const chosen = m ? (m[1] || m[2]) : firstPart;
  return chosen.length ? chosen : 'Unknown';
}
function takeFirstNWords(text, n) {
  return (text || '').replace(/\s+/g, ' ').trim().split(' ').slice(0, n).join('_');
}
function sanitizeFilename(s) {
  return (s || '')
    .replace(/[\u0000-\u001F]/g, '')
    .replace(/[\/\\:\*\?"<>\|]/g, '_')
    .replace(/\s+/g, '_')
    .slice(0, 180);
}
function nowUTC() {
  return Utilities.formatDate(new Date(), "UTC", "yyyy-MM-dd'T'HH:mm:ss'Z'");
}
function timestampSafe() {
  return Utilities.formatDate(new Date(), "UTC", "yyyyMMdd_HHmmss'Z'");
}
function keyFor(threadId) {
  return `exported_${threadId}`;
}
function hashSafe(s) {
  // simple non-crypto hash for deterministic short ids
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h*31 + s.charCodeAt(i))>>>0;
  return h.toString(16);
}

/*** ==== RENDERERS ==== ***/
function buildPlainTextThread(messages) {
  const parts = [];
  messages.forEach((m, idx) => {
    const msgId = m.getHeader("Message-ID") || "(unknown)";
    parts.push(`----- Message ${idx+1} of ${messages.length} -----`);
    parts.push(`Date (UTC): ${Utilities.formatDate(m.getDate(), "UTC", "yyyy-MM-dd HH:mm:ss'Z'")}`);
    parts.push(`From: ${m.getFrom()}`);
    parts.push(`To: ${m.getTo() || ''}`);
    const cc = m.getCc(); if (cc) parts.push(`Cc: ${cc}`);
    parts.push(`Subject: ${m.getSubject() || ''}`);
    parts.push(`Message-ID: ${msgId}`);
    parts.push('');
    parts.push(m.getPlainBody() || '');
    parts.push('\n');
  });
  return parts.join('\n');
}

function buildHtmlThread(messages) {
  const blocks = messages.map((m, idx) => {
    const msgId = m.getHeader("Message-ID") || "";
    const hdr = [
      `<b>Date (UTC):</b> ${Utilities.formatDate(m.getDate(), "UTC", "yyyy-MM-dd HH:mm:ss'Z'")}`,
      `<b>From:</b> ${safe(m.getFrom())}`,
      `<b>To:</b> ${safe(m.getTo() || '')}`,
      `<b>Cc:</b> ${safe(m.getCc() || '')}`,
      `<b>Subject:</b> ${safe(m.getSubject() || '')}`,
      `<b>Message-ID:</b> ${safe(msgId)}`
    ].join("<br/>");
    return `<hr><div>${hdr}<div style="margin-top:6px">${m.getBody()}</div></div>`;
  }).join("\n");

  return `<html><head><meta charset="UTF-8"></head><body>${blocks}</body></html>`;
}
function safe(s){return String(s).replace(/</g,"&lt;").replace(/>/g,"&gt;");}

function textToPdfViaDoc(text, filename) {
  const doc = DocumentApp.create(`TMP_${Date.now()}`);
  try {
    doc.getBody().clear().appendParagraph(text);
    doc.saveAndClose();
    const pdfBlob = DriveApp.getFileById(doc.getId()).getAs(MimeType.PDF);
    pdfBlob.setName(filename);
    return pdfBlob;
  } finally {
    try { DriveApp.getFileById(doc.getId()).setTrashed(true); } catch (e) {}
  }
}
function htmlToPdf(html, filename) {
  const blob = Utilities.newBlob(html, 'text/html', 'thread.html').getAs('application/pdf');
  blob.setName(filename);
  return blob;
}

/*** ==== CSV ==== ***/
function toCSV(rows) {
  return rows.map(r => r.map(cell => csvSafe(cell)).join(",")).join("\n");
}
function csvSafe(v) {
  if (v == null) return "";
  const s = String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g,'""')}"` : s;
}
