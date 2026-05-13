# FederHub Team Beta Client

This folder contains the current Team Beta edge-node client.

## What is included

- Electron desktop client for the local operator workflow
- Alpha authentication from the desktop client
- Dockerized training with a read-only dataset mount
- PyTorch checkpoint selection and inspection
- Checkpoint-aware CSV schema validation
- Gamma update delivery after training completes
- Synthetic healthcare demo bundles for fracture and tumor detection

## Folder layout

- `main.js`: Electron main process and Docker execution flow
- `preload.js`: secure bridge between the renderer and Electron APIs
- `Dockerfile`: container image for the training worker
- `requirements.txt`: Python dependencies used inside the container
- `src/`: desktop UI files
- `ml/train.py`: checkpoint-aware training worker
- `ml/inspect_checkpoint.py`: reads `.pt` metadata to infer dataset requirements
- `grpc_weight_sender.py`: streams mathematical model updates to Gamma
- `demo-client-data/`: sample datasets and checkpoints for demos

## Prerequisites

1. Install Node.js and npm.
2. Install Python 3.
3. Install Docker Desktop and ensure the `docker` CLI is available.
4. Start the Alpha backend and Gamma gRPC server.
5. Install Electron dependencies from this folder:

```bash
npm install
```

## Run the desktop client

```bash
npm start
```

## Demo bundles

- `demo-client-data/fracture-detection/`
  - `fracture_dataset.csv`
  - `fracture_model.pt`
- `demo-client-data/tumor-detection/`
  - `tumor_dataset.csv`
  - `tumor_model.pt`
- `demo-client-data/sample_client_data.csv`
  - `demo-client-data/sample_model.pt`

## Desktop flow

1. Launch the Electron app.
2. Enter operator credentials and authenticate with Alpha.
3. Choose a `.pt` checkpoint file.
4. Choose the matching dataset folder.
5. Review the inferred dataset requirements in the UI.
6. Validate the selected checkpoint and dataset.
7. Click `Start Training`.

## Output artifacts

The app writes updated weights and a run summary to the Electron user-data output directory. Updated checkpoints are saved as `updated_<original-checkpoint-name>.pt`.

## Notes

- The selected dataset folder is mounted read-only into Docker so source data remains local during training.
- The default Gamma server value is `host.docker.internal:50051` so the Dockerized worker can reach Gamma running on the host machine.
- The client restores the last authenticated Alpha session on launch until the operator logs out.
