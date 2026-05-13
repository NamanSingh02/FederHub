const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("federHub", {
  selectFolder: () => ipcRenderer.invoke("dialog:select-folder"),
  selectModelFile: () => ipcRenderer.invoke("dialog:select-model-file"),
  getAuthSession: () => ipcRenderer.invoke("auth:get-session"),
  login: (payload) => ipcRenderer.invoke("auth:login", payload),
  logout: () => ipcRenderer.invoke("auth:logout"),
  getJobDetails: (payload) => ipcRenderer.invoke("jobs:get-details", payload),
  inspectCheckpoint: (checkpointPath) =>
    ipcRenderer.invoke("training:inspect-checkpoint", checkpointPath),
  validateInputs: (payload) => ipcRenderer.invoke("training:validate-inputs", payload),
  startTraining: (payload) => ipcRenderer.invoke("training:start", payload),
  downloadGlobalModel: (payload) => ipcRenderer.invoke("model:download", payload),
  onTrainingProgress: (callback) => {
    const handler = (_event, payload) => callback(payload);
    ipcRenderer.on("training:progress", handler);
    return () => ipcRenderer.removeListener("training:progress", handler);
  },
});
