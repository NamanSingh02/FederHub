# dummy_client.py
import grpc
import federation_pb2
import federation_pb2_grpc
import time

def run_dummy_clients():
    # Connecting to the local gRPC server
    channel = grpc.insecure_channel('localhost:50051')
    stub = federation_pb2_grpc.AggregatorStub(channel)

    # Replicating the Phase 1 mock scenario
    mock_clients = [
        ("Hospital A", 300, [0.10, 0.25, 0.38, 0.47, 0.60, 0.72]),
        ("Hospital B", 500, [0.15, 0.20, 0.42, 0.50, 0.55, 0.68]),
        ("Bank C", 200, [0.12, 0.30, 0.35, 0.44, 0.63, 0.75]),
    ]

    for name, samples, weights in mock_clients:
        print(f"[CLIENT] {name} sending local model update...")
        request = federation_pb2.WeightUpdate(
            client_id=name,
            sample_count=samples,
            weights=weights
        )
        
        response = stub.SubmitWeightUpdate(request)
        print(f"[CLIENT] Server Response: {response.message}\n")
        time.sleep(1) # Slight delay to simulate network latency

if __name__ == '__main__':
    run_dummy_clients()