const MAX_FILE_SIZE = 60 * 1024 * 1024;
const ALLOWED_EXTENSIONS = ["pdf", "doc", "docx"];

const elements = {
  serviceState: document.querySelector("#serviceState"),
  dropzone: document.querySelector("#dropzone"),
  fileInput: document.querySelector("#fileInput"),
  browseButton: document.querySelector("#browseButton"),
  fileCard: document.querySelector("#fileCard"),
  fileName: document.querySelector("#fileName"),
  fileMeta: document.querySelector("#fileMeta"),
  removeFile: document.querySelector("#removeFile"),
  startButton: document.querySelector("#startButton"),
  processingPanel: document.querySelector("#processingPanel"),
  phaseText: document.querySelector("#phaseText"),
  progressValue: document.querySelector("#progressValue"),
  progressBar: document.querySelector("#progressBar"),
  pageProgress: document.querySelector("#pageProgress"),
  processSteps: document.querySelector("#processSteps"),
  resultPanel: document.querySelector("#resultPanel"),
  statPages: document.querySelector("#statPages"),
  statEntities: document.querySelector("#statEntities"),
  statVisuals: document.querySelector("#statVisuals"),
  downloadButton: document.querySelector("#downloadButton"),
  newTaskButton: document.querySelector("#newTaskButton"),
  previewPanel: document.querySelector("#previewPanel"),
  previewEmpty: document.querySelector("#previewEmpty"),
  pdfPreview: document.querySelector("#pdfPreview"),
  openPreview: document.querySelector("#openPreview"),
  errorBox: document.querySelector("#errorBox"),
  errorText: document.querySelector("#errorText"),
  retryButton: document.querySelector("#retryButton"),
};

let selectedFile = null;
let activeJobId = null;
let pollTimer = null;

function openFilePicker() {
  if (!elements.startButton.disabled && elements.fileCard.hidden === false) {
    return;
  }
  elements.fileInput.click();
}

elements.dropzone.addEventListener("click", openFilePicker);
elements.dropzone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    openFilePicker();
  }
});

elements.browseButton.addEventListener("click", (event) => {
  event.stopPropagation();
  elements.fileInput.click();
});

elements.fileInput.addEventListener("change", () => {
  const [file] = elements.fileInput.files;
  if (file) selectFile(file);
});

["dragenter", "dragover"].forEach((eventName) => {
  elements.dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    elements.dropzone.classList.add("is-dragging");
  });
});

["dragleave", "drop"].forEach((eventName) => {
  elements.dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    elements.dropzone.classList.remove("is-dragging");
  });
});

elements.dropzone.addEventListener("drop", (event) => {
  const [file] = event.dataTransfer.files;
  if (file) selectFile(file);
});

elements.removeFile.addEventListener("click", resetWorkspace);
elements.newTaskButton.addEventListener("click", resetWorkspace);
elements.retryButton.addEventListener("click", resetWorkspace);
elements.startButton.addEventListener("click", startJob);

function selectFile(file) {
  const extension = file.name.split(".").pop()?.toLowerCase() || "";
  if (!ALLOWED_EXTENSIONS.includes(extension)) {
    showError("请选择 PDF、DOC 或 DOCX 文件。", false);
    return;
  }
  if (file.size > MAX_FILE_SIZE) {
    showError("文件超过 60 MB，请压缩后再试。", false);
    return;
  }

  selectedFile = file;
  elements.fileName.textContent = file.name;
  elements.fileMeta.textContent = `${extension.toUpperCase()} · ${formatBytes(file.size)}`;
  elements.dropzone.hidden = true;
  elements.fileCard.hidden = false;
  elements.startButton.disabled = false;
  elements.errorBox.hidden = true;
}

async function startJob() {
  if (!selectedFile) return;
  setBusy(true);
  elements.processingPanel.hidden = false;
  elements.resultPanel.hidden = true;
  elements.errorBox.hidden = true;
  elements.previewPanel.hidden = false;
  elements.previewEmpty.hidden = false;
  elements.previewEmpty.querySelector("strong").textContent = "合同正在处理中";
  elements.previewEmpty.querySelector("p").textContent = "完成后会自动在这里加载脱敏 PDF。";
  elements.pdfPreview.hidden = true;
  elements.openPreview.hidden = true;
  updateProgress({ progress: 5, phase: "正在上传合同", current_page: 0, total_pages: 0 });

  try {
    const response = await fetch("/api/jobs", {
      method: "POST",
      headers: {
        "Content-Type": "application/octet-stream",
        "X-Filename": encodeURIComponent(selectedFile.name),
      },
      body: selectedFile,
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "上传失败，请稍后重试。");
    }
    activeJobId = payload.job_id;
    pollJob();
  } catch (error) {
    showError(error.message || "无法创建处理任务。", true);
  }
}

async function pollJob() {
  if (!activeJobId) return;
  try {
    const response = await fetch(`/api/jobs/${activeJobId}`, { cache: "no-store" });
    const job = await response.json();
    if (!response.ok) throw new Error(job.detail || "无法读取任务状态。");
    updateProgress(job);

    if (job.status === "complete") {
      showResult(job);
      return;
    }
    if (job.status === "failed") {
      showError(job.error || "处理失败，请检查服务配置后重试。", true);
      return;
    }
    pollTimer = window.setTimeout(pollJob, 1200);
  } catch (error) {
    showError(error.message || "连接中断，请重新提交。", true);
  }
}

function updateProgress(job) {
  const progress = Math.max(0, Math.min(100, Number(job.progress) || 0));
  elements.phaseText.textContent = job.phase || "正在处理合同";
  elements.progressValue.textContent = `${progress}%`;
  elements.progressBar.style.width = `${progress}%`;
  elements.progressBar.parentElement.setAttribute("aria-valuenow", String(progress));
  if (job.total_pages) {
    elements.pageProgress.textContent = `已完成 ${job.current_page || 0} / ${job.total_pages} 页`;
  } else {
    elements.pageProgress.textContent = "正在读取文档页数";
  }

  const steps = [...elements.processSteps.querySelectorAll("li")];
  steps.forEach((step, index) => {
    const threshold = Number(step.dataset.threshold);
    const nextThreshold = Number(steps[index + 1]?.dataset.threshold || 101);
    step.classList.toggle("is-complete", progress >= nextThreshold);
    step.classList.toggle("is-active", progress >= threshold && progress < nextThreshold);
  });
}

function showResult(job) {
  window.clearTimeout(pollTimer);
  const summary = job.summary || {};
  const previewUrl = `/api/jobs/${activeJobId}/preview`;
  const downloadUrl = `/api/jobs/${activeJobId}/download`;
  elements.processingPanel.hidden = true;
  elements.resultPanel.hidden = false;
  elements.previewPanel.hidden = false;
  elements.previewEmpty.hidden = true;
  elements.pdfPreview.hidden = false;
  elements.openPreview.hidden = false;
  elements.statPages.textContent = summary.pages ?? "—";
  elements.statEntities.textContent = summary.entities ?? "—";
  elements.statVisuals.textContent =
    Number(summary.stamps || 0) + Number(summary.signature_fields || 0);
  elements.downloadButton.href = downloadUrl;
  elements.openPreview.href = previewUrl;
  elements.pdfPreview.src = previewUrl;
  setBusy(false, true);
  elements.previewPanel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function showError(message, afterSubmission) {
  window.clearTimeout(pollTimer);
  elements.errorText.textContent = message;
  elements.errorBox.hidden = false;
  elements.processingPanel.hidden = true;
  elements.resultPanel.hidden = true;
  elements.previewPanel.hidden = false;
  elements.previewEmpty.hidden = false;
  elements.previewEmpty.querySelector("strong").textContent = "这次暂时无法生成预览";
  elements.previewEmpty.querySelector("p").textContent = "请根据上方错误提示检查后重新提交。";
  elements.pdfPreview.hidden = true;
  elements.openPreview.hidden = true;
  if (afterSubmission) setBusy(false);
}

function setBusy(isBusy, isComplete = false) {
  elements.startButton.disabled = isBusy || isComplete || !selectedFile;
  elements.removeFile.disabled = isBusy;
  elements.dropzone.setAttribute("aria-disabled", String(isBusy));
  if (isBusy) {
    elements.startButton.querySelector("span").textContent = "正在处理";
  } else {
    elements.startButton.querySelector("span").textContent = "开始脱敏";
  }
}

function resetWorkspace() {
  window.clearTimeout(pollTimer);
  activeJobId = null;
  selectedFile = null;
  elements.fileInput.value = "";
  elements.dropzone.hidden = false;
  elements.fileCard.hidden = true;
  elements.processingPanel.hidden = true;
  elements.resultPanel.hidden = true;
  elements.previewPanel.hidden = false;
  elements.errorBox.hidden = true;
  elements.pdfPreview.removeAttribute("src");
  elements.pdfPreview.hidden = true;
  elements.openPreview.hidden = true;
  elements.previewEmpty.hidden = false;
  elements.previewEmpty.querySelector("strong").textContent = "脱敏完成后，PDF 会显示在这里";
  elements.previewEmpty.querySelector("p").textContent =
    "你可以逐页检查黑框位置，再决定是否下载和流转。";
  elements.startButton.disabled = true;
  elements.removeFile.disabled = false;
  updateProgress({ progress: 5, phase: "正在准备合同", current_page: 0, total_pages: 0 });
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

async function checkService() {
  try {
    const response = await fetch("/health", { cache: "no-store" });
    if (!response.ok) throw new Error();
    elements.serviceState.className = "service-state is-ready";
    elements.serviceState.querySelector("span:last-child").textContent = "服务已就绪";
  } catch {
    elements.serviceState.className = "service-state is-error";
    elements.serviceState.querySelector("span:last-child").textContent = "服务未连接";
  }
}

checkService();
