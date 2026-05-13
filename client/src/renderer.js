const folderInput = document.getElementById("selected-folder");
const checkpointInput = document.getElementById("checkpoint-path");
const pickFolderButton = document.getElementById("pick-folder");
const pickModelFileButton = document.getElementById("pick-model-file");
const form = document.getElementById("client-form");
const logOutput = document.getElementById("log-output");
const statusPill = document.getElementById("status-pill");
const startButton = document.getElementById("start-training");
const validateButton = document.getElementById("validate-inputs");
const authenticateButton = document.getElementById("authenticate");
const logoutButton = document.getElementById("logout");
const requirementsCopy = document.getElementById("dataset-requirements-copy");
const requirementsColumns = document.getElementById("dataset-requirements-columns");
const checkpointRequirements = document.getElementById("checkpoint-requirements");
const authSummary = document.getElementById("auth-summary");
const sessionSummary = document.getElementById("session-summary");
const validationSummary = document.getElementById("validation-summary");
const resultSummary = document.getElementById("result-summary");
const progressList = document.getElementById("progress-list");
const jobSummary = document.getElementById("job-summary");

let activeSession = null;

function setStatus(label, className) {
  statusPill.textContent = label;
  statusPill.className = `badge ${className}`.trim();
}

function setLog(text) {
  logOutput.textContent = text;
}

function setAuthSummary(session = null, message = "") {
  if (message) {
    authSummary.textContent = message;
    sessionSummary.textContent = "Authentication is required before checkpoint selection.";
    return;
  }

  if (!session || !session.accessToken) {
    authSummary.textContent = "Not authenticated yet.";
    sessionSummary.textContent = "Sign in to unlock checkpoint selection and training.";
    return;
  }

  authSummary.textContent = `Authenticated as ${session.email} (${session.role || "user"}) via ${session.apiBaseUrl}`;
  sessionSummary.textContent = `Session established at ${new Date(
    session.authenticatedAt || Date.now()
  ).toLocaleString()}.`;
}

function updateAuthControls() {
  const isAuthenticated = Boolean(activeSession && activeSession.accessToken);
  pickModelFileButton.disabled = !isAuthenticated;
  logoutButton.disabled = !isAuthenticated;
}

function applySession(session) {
  activeSession = session && session.accessToken ? session : null;
  setAuthSummary(activeSession);
  updateAuthControls();
}

function requireAuthenticatedSession(actionLabel) {
  if (activeSession && activeSession.accessToken) {
    return true;
  }

  setStatus("Authentication Required", "error");
  setAuthSummary(null, `Sign in before ${actionLabel}.`);
  setLog(`Sign in before ${actionLabel}.`);
  return false;
}

function resetRequirements() {
  requirementsCopy.textContent =
    "Select a checkpoint to load the expected dataset structure.";
  requirementsColumns.textContent = "";
  checkpointRequirements.textContent =
    "The required CSV schema appears after checkpoint inspection.";
}

function resetProgress() {
  Array.from(progressList.querySelectorAll("li")).forEach((item) => {
    item.dataset.state = "pending";
    item.querySelector("strong").textContent = "Pending";
    item.title = "";
  });
}

function updateProgress(step, state, message) {
  const item = progressList.querySelector(`[data-step="${step}"]`);
  if (!item) {
    return;
  }

  item.dataset.state = state;
  item.querySelector("strong").textContent =
    state === "running"
      ? "In progress"
      : state === "completed"
        ? "Completed"
        : state === "failed"
          ? "Failed"
          : "Pending";
  if (message) {
    item.title = message;
  }
}

function setResultSummary(summary = null) {
  const values = summary
    ? {
        "Authenticated User":
          activeSession?.email || summary.operator || "Not available",
        "Target Job": summary.targetJob || "Not available",
        "Updated model": summary.localWeightsPath || "Not available",
        "Run summary": summary.localRunSummaryPath || "Not available",
        Checkpoint: summary.checkpoint || "Not available",
        Dataset: summary.dataset || "Not available",
        "Aggregation Stream": summary.gammaStreamStatus || "Not available",
      }
    : {
        "Authenticated User": activeSession?.email || "Not available yet",
        "Target Job": "Not available yet",
        "Updated model": "Not available yet",
        "Run summary": "Not available yet",
        Checkpoint: "Not available yet",
        Dataset: "Not available yet",
        "Aggregation Stream": "Not available yet",
      };

  resultSummary.innerHTML = Object.entries(values)
    .map(
      ([label, value]) => `<div><dt>${label}</dt><dd>${value}</dd></div>`
    )
    .join("");
}

function setButtonsDisabled(isDisabled) {
  startButton.disabled = isDisabled;
  validateButton.disabled = isDisabled;
  pickFolderButton.disabled = isDisabled;
  pickModelFileButton.disabled =
    isDisabled || !(activeSession && activeSession.accessToken);
  authenticateButton.disabled = isDisabled;
  logoutButton.disabled = isDisabled || !(activeSession && activeSession.accessToken);
}

// --- UPDATED: Removed clientId mapping ---
function buildPayload() {
  return {
    username: document.getElementById("username").value.trim(),
    password: document.getElementById("password").value,
    alphaApiUrl: document.getElementById("alpha-api-url").value.trim(),
    checkpointPath: checkpointInput.value.trim(),
    selectedFolder: folderInput.value.trim(),
    gammaServer: document.getElementById("gamma-server").value.trim(),
    jobId: document.getElementById("job-id").value.trim(), 
    // clientId has been removed. Electron will auto-inject it securely from the session in main.js.
  };
}

async function authenticateOperator() {
  const payload = buildPayload();

  if (!payload.username) {
    setStatus("Email Needed", "error");
    setAuthSummary(null, "Enter the operator email before authenticating.");
    return;
  }

  if (!payload.password) {
    setStatus("Password Needed", "error");
    setAuthSummary(null, "Enter the operator password before authenticating.");
    return;
  }

  setButtonsDisabled(true);
  updateProgress("auth", "running", "Signing in to FederHub.");
  setStatus("Authenticating", "info");

  try {
    const result = await window.federHub.login(payload);
    if (result.ok) {
      updateProgress("auth", "completed", result.summary);
      setStatus("Authenticated", "success");
      applySession(result.session);
      setLog(`${result.summary}\n\nJWT stored for the current desktop session.`);
    } else {
      updateProgress("auth", "failed", result.summary);
      setStatus("Auth Failed", "error");
      applySession(null);
      setAuthSummary(null, result.summary);
      setLog(result.summary);
    }
  } catch (error) {
    const message =
      error && error.message
        ? error.message
        : "Authentication failed unexpectedly.";
    updateProgress("auth", "failed", message);
    setStatus("Auth Failed", "error");
    applySession(null);
    setAuthSummary(null, message);
    setLog(message);
  } finally {
    setButtonsDisabled(false);
  }
}

async function runTraining(startFn, options = {}) {
  const payload = buildPayload();

  if (!requireAuthenticatedSession("starting training")) {
    return;
  }

  if (!payload.checkpointPath) {
    setStatus("Checkpoint Needed", "error");
    setLog("Select a PyTorch checkpoint before starting training.");
    return;
  }

  if (!payload.selectedFolder) {
    setStatus("Folder Needed", "error");
    setLog("Choose a local dataset folder before starting training.");
    return;
  }
  
  if (!payload.jobId) {
    setStatus("Job ID Needed", "error");
    setLog("Please enter a Target Job ID before starting training.");
    return;
  }

  setButtonsDisabled(true);
  resetProgress();
  setResultSummary(null);
  setStatus("Training", "warning");
  setLog(options.startMessage || "Preparing training...");
  validationSummary.textContent =
    "Validation will run as part of training startup.";

  try {
    const result = await startFn(payload);
    const combinedOutput = [result.stdout, result.stderr]
      .filter(Boolean)
      .join("\n");

    if (result.ok) {
      setStatus("Completed", "success");
      setLog(combinedOutput || "Training completed successfully.");
      if (result.auth?.session) {
        applySession(result.auth.session);
      }
      validationSummary.textContent =
        result.validation?.summary || "Validation completed successfully.";
      setResultSummary(result.summary);
    } else {
      setStatus("Failed", "error");
      setLog(combinedOutput || "Training did not complete successfully.");
      if (result.auth?.summary) {
        if (result.auth?.session) {
          applySession(result.auth.session);
        } else {
          setAuthSummary(result.auth?.session || null, result.auth.summary);
        }
      }
      validationSummary.textContent =
        result.validation?.summary || "Validation did not complete successfully.";
    }
  } catch (error) {
    setStatus("Failed", "error");
    setLog(
      error && error.message
        ? `Training failed to start: ${error.message}`
        : "Training could not be started due to an unexpected error."
    );
  } finally {
    setButtonsDisabled(false);
  }
}

async function validateInputs() {
  const payload = buildPayload();
  resetProgress();
  setResultSummary(null);

  if (!requireAuthenticatedSession("validating inputs")) {
    return;
  }

  if (!payload.checkpointPath) {
    setStatus("Checkpoint Needed", "error");
    validationSummary.textContent =
      "Select a PyTorch checkpoint before validating inputs.";
    return;
  }

  if (!payload.selectedFolder) {
    setStatus("Folder Needed", "error");
    validationSummary.textContent =
      "Choose a local dataset folder before validating inputs.";
    return;
  }

  setButtonsDisabled(true);
  setStatus("Validating", "info");
  validationSummary.textContent =
    "Validating checkpoint and dataset compatibility.";
  jobSummary.textContent = "Target job has not been verified yet.";
  updateProgress("inspect", "running", "Inspecting checkpoint and dataset.");

  try {
    const jobResult = await window.federHub.getJobDetails(payload);
    if (!jobResult.ok) {
      updateProgress("inspect", "failed", jobResult.summary);
      setStatus("Validation Failed", "error");
      jobSummary.textContent = jobResult.summary;
      validationSummary.textContent = "Target job validation failed.";
      setLog(jobResult.summary);
      return;
    }

    jobSummary.textContent = `${jobResult.summary} Local epochs: ${jobResult.job.local_epochs}. Expected clients: ${jobResult.job.expected_clients}.`;

    const result = await window.federHub.validateInputs(payload);
    if (result.ok) {
      updateProgress("inspect", "completed", result.summary);
      setStatus("Ready", "success");
      validationSummary.textContent = `${result.summary} Dataset file: ${result.datasetPath}`;
      setLog(
        `${jobResult.summary}\n\nValidation successful.\n\nDataset file:\n${result.datasetPath}\n\nRequired columns:\n${result.columns.join(", ")}`
      );
    } else {
      updateProgress("inspect", "failed", result.summary);
      setStatus("Validation Failed", "error");
      validationSummary.textContent = result.summary;
      setLog(result.summary);
    }
  } catch (error) {
    updateProgress("inspect", "failed", "Validation failed unexpectedly.");
    setStatus("Validation Failed", "error");
    validationSummary.textContent =
      error && error.message ? error.message : "Validation failed unexpectedly.";
  } finally {
    setButtonsDisabled(false);
  }
}

pickFolderButton.addEventListener("click", async () => {
  const folder = await window.federHub.selectFolder();
  if (folder) {
    folderInput.value = folder;
    setStatus("Folder Ready", "info");
    setLog(
      `Selected dataset folder:\n${folder}\n\nCheckpoint: ${checkpointInput.value || "not selected"}\n\nThe folder will be mounted read-only during training.`
    );
  }
});

pickModelFileButton.addEventListener("click", async () => {
  if (!requireAuthenticatedSession("selecting a checkpoint")) {
    return;
  }

  const modelFile = await window.federHub.selectModelFile();
  if (modelFile) {
    checkpointInput.value = modelFile;
    setStatus("Checkpoint Ready", "info");
    resetRequirements();
    const inspection = await window.federHub.inspectCheckpoint(modelFile);
    checkpointRequirements.textContent = inspection.summary;
    if (inspection.columns && inspection.columns.length > 0) {
      requirementsColumns.textContent = inspection.columns.join(", ");
    } else {
      const fallbackMatch = inspection.summary.match(
        /Expected CSV columns remain (.+?)\.$/
      );
      if (fallbackMatch) {
        requirementsColumns.textContent = fallbackMatch[1];
      }
    }
    setLog(
      `Selected checkpoint:\n${modelFile}\n\n${inspection.summary}\n\nThe checkpoint will be loaded before training starts.`
    );
  }
});

authenticateButton.addEventListener("click", async () => {
  await authenticateOperator();
});

logoutButton.addEventListener("click", async () => {
  try {
    await window.federHub.logout();
  } catch {
    // Keep local reset behavior even if file cleanup fails.
  }

  activeSession = null;
  checkpointInput.value = "";
  resetRequirements();
  resetProgress();
  setResultSummary(null);
  setAuthSummary(null);
  updateAuthControls();
  setStatus("Logged Out", "muted");
  setLog("Session cleared. Sign in to continue.");
});

window.federHub.onTrainingProgress((payload) => {
  updateProgress(payload.step, payload.state, payload.message);
});

validateButton.addEventListener("click", async () => {
  await validateInputs();
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  await runTraining(window.federHub.startTraining, {
    startMessage:
      "Preparing the runtime...\n\n1. Sign in to FederHub\n2. Inspect checkpoint and dataset\n3. Locate training container\n4. Load the dataset into the runtime\n5. Train the model\n6. Save the updated artifacts\n7. Stream weight updates to the aggregation server",
  });
});

// --- Job ID live validation ---
const jobIdInput = document.getElementById("job-id");
let jobValidationTimeout = null;

jobIdInput.addEventListener("input", () => {
  jobSummary.textContent = "Target job has not been verified yet.";
  jobIdInput.dataset.state = "pending";
});

jobIdInput.addEventListener("blur", async () => {
  const jobId = jobIdInput.value.trim();
  if (!jobId) return;
  if (!activeSession || !activeSession.accessToken) return;

  clearTimeout(jobValidationTimeout);
  jobValidationTimeout = setTimeout(async () => {
    jobSummary.textContent = "Checking job...";
    jobIdInput.dataset.state = "checking";
    try {
      const result = await window.federHub.getJobDetails({ jobId });
      if (result.ok) {
        jobSummary.textContent = `${result.summary} Local epochs: ${result.job.local_epochs}. Expected clients: ${result.job.expected_clients}.`;
        jobIdInput.dataset.state = "valid";
      } else {
        jobSummary.textContent = result.summary;
        jobIdInput.dataset.state = "invalid";
      }
    } catch {
      jobSummary.textContent = "Could not validate job ID.";
      jobIdInput.dataset.state = "invalid";
    }
  }, 400);
});

// --- Global model download ---
const downloadModelBtn = document.getElementById("download-model");
if (downloadModelBtn) {
  downloadModelBtn.addEventListener("click", async () => {
    const jobId = jobIdInput.value.trim();

    if (!activeSession) {
      setStatus("Authentication Required", "error");
      setLog("Sign in before downloading the global model.");
      return;
    }
    if (!jobId) {
      setStatus("Job ID Needed", "error");
      setLog("Enter a Target Job ID before downloading the global model.");
      return;
    }

    setButtonsDisabled(true);
    setStatus("Downloading", "info");
    setLog("Fetching global model from server and converting to PyTorch checkpoint...\n\nThis requires Docker — the training container will run the conversion.");

    try {
      const result = await window.federHub.downloadGlobalModel({
        apiUrl: document.getElementById("alpha-api-url").value.trim(),
        jobId,
        accessToken: activeSession.accessToken,
      });

      if (result.canceled) {
        setStatus("Cancelled", "muted");
        setLog("Model download cancelled.");
        return;
      }

      if (result.ok) {
        setStatus("Downloaded", "success");
        setLog(
          `Global model checkpoint saved as a PyTorch .pt file.\n\n` +
          `Job: ${result.jobName || jobId}\n` +
          `Round: ${result.roundNumber || "latest"}\n` +
          `File: ${result.ptPath}\n\n` +
          `You can now select this file as the checkpoint for the next training round.`
        );
      } else {
        setStatus("Download Failed", "error");
        setLog(`Model download failed:\n\n${result.error}`);
      }
    } catch (err) {
      setStatus("Download Failed", "error");
      setLog(`Download error: ${err && err.message ? err.message : "Unexpected error."}`);
    } finally {
      setButtonsDisabled(false);
    }
  });
}

window.addEventListener("DOMContentLoaded", async () => {
  try {
    const session = await window.federHub.getAuthSession();
    applySession(session);
  } catch {
    applySession(null);
  }
  jobSummary.textContent = "Target job has not been verified yet.";
});
