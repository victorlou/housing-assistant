"""MLflow logging, evaluation, and serving endpoint creation."""

import json

import mlflow
from agent import agent_graph
from mlflow.models import ModelSignature


def log_agent(target: str = "dev"):
    """
    Log the agent graph to MLflow.

    Args:
        target: Deployment target ("dev", "staging", or "prod")
    """
    # Start MLflow run
    with mlflow.start_run(run_name=f"housing-agent-{target}"):
        # Define input/output schema
        input_schema = {
            "messages": list,  # List of message dicts
            "user_id": str,
            "session_id": str,
        }
        output_schema = {
            "messages": list,  # List of message dicts
            "suburb_results": dict,  # Ranked suburbs
        }

        signature = ModelSignature(
            inputs=input_schema,
            outputs=output_schema,
        )

        # Input example (for serving documentation)
        input_example = {
            "messages": [{"role": "user", "content": "Find suburbs under $700/week"}],
            "user_id": "user-123",
            "session_id": "session-456",
        }

        # Log model to MLflow
        model_info = mlflow.langchain.log_model(
            lc_model=agent_graph,
            artifact_path="housing_agent",
            input_example=input_example,
            signature=signature,
            pip_requirements=[
                "langgraph>=0.2",
                "langchain-core>=0.3",
                "langchain-databricks>=0.3",
                "mlflow>=2.16",
                "databricks-sdk",
                "psycopg2-binary",
            ],
        )

        # Log system prompt as artifact
        with open("agents/prompts/system.md") as f:
            mlflow.log_text(f.read(), "prompts/system.md")

        # Log tags for tracking
        mlflow.set_tags(
            {
                "environment": target,
                "framework": "langgraph",
                "owner": "naineel",
                "model_type": "agent",
            }
        )

        print(f"✅ Agent logged to MLflow: {model_info.model_uri}")
        return model_info


def evaluate_agent(model_uri: str):
    """
    Evaluate the agent against golden dataset.

    Args:
        model_uri: MLflow model URI (e.g., "runs:/.../housing_agent")
    """
    # Load golden dataset
    try:
        with open("agents/eval/golden_dataset.jsonl") as f:
            eval_data = [json.loads(line) for line in f if line.strip()]
    except FileNotFoundError:
        print("⚠️  No golden dataset found. Skipping evaluation.")
        print("   Create agents/eval/golden_dataset.jsonl with test cases.")
        return None

    if not eval_data:
        print("⚠️  Golden dataset is empty. Skipping evaluation.")
        return None

    # Run evaluation
    print(f"📊 Evaluating {len(eval_data)} test cases...")
    results = mlflow.evaluate(
        model=model_uri,
        data=eval_data,
        evaluators=["default"],
    )

    print(f"✅ Evaluation complete")
    print(f"   Metrics: {results.metrics}")

    return results


def register_to_catalog(run_id: str):
    """
    Register model to Unity Catalog.

    Args:
        run_id: MLflow run ID
    """
    model_name = "housing.app.housing_agent"

    try:
        model_uri = f"runs:/{run_id}/housing_agent"
        mlflow.register_model(
            model_uri=model_uri,
            name=model_name,
            tags={
                "framework": "langgraph",
                "owner": "naineel",
            },
        )
        print(f"✅ Model registered to Unity Catalog: {model_name}")
    except Exception as e:
        print(f"⚠️  Could not register to Unity Catalog: {e}")
        print(f"   Ensure Unity Catalog is available and you have permissions.")


def deploy(target: str = "dev"):
    """
    Full deployment: log, evaluate, and register.

    Args:
        target: Deployment target ("dev", "staging", or "prod")
    """
    print(f"🚀 Deploying Housing Assistant agent to {target}...")

    # 1. Log model
    model_info = log_agent(target)

    # 2. Evaluate (optional, requires golden dataset)
    evaluate_agent(model_info.model_uri)

    # 3. Register to Unity Catalog
    # Extract run ID from model URI (format: runs:/run_id/...)
    run_id = model_info.model_uri.split("/")[1]
    register_to_catalog(run_id)

    print(f"✅ Deployment complete!")
    print(f"   Model: {model_info.model_uri}")
    print(f"   Catalog: housing.app.housing_agent")
    print(f"   Next: Create serving endpoint via Terraform")


if __name__ == "__main__":
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "dev"
    deploy(target)
