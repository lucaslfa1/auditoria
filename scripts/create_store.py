import os
import time
from google.cloud import discoveryengine

def create_unstructured_store():
    project_id = "auditoria-nstech"
    location = "global"

    client = discoveryengine.DataStoreServiceClient()
    parent = client.collection_path(project=project_id, location=location, collection="default_collection")
    
    data_store_id = "auditoria-docs-rag"
    
    data_store = discoveryengine.DataStore(
        display_name="Auditoria Docs RAG",
        industry_vertical=discoveryengine.IndustryVertical.GENERIC,
        solution_types=[discoveryengine.SolutionType.SOLUTION_TYPE_SEARCH],
        content_config=discoveryengine.DataStore.ContentConfig.CONTENT_REQUIRED,
        # CONTENT_REQUIRED usually means Unstructured? Let's check documentation.
        # Actually, let's just do it via API if possible.
    )

    request = discoveryengine.CreateDataStoreRequest(
        parent=parent,
        data_store=data_store,
        data_store_id=data_store_id
    )

    try:
        print("Criando novo Data Store...")
        operation = client.create_data_store(request=request)
        result = operation.result()
        print(f"Data Store criado: {result.name}")
    except Exception as e:
        print(f"Erro ao criar Data Store: {e}")

if __name__ == "__main__":
    create_unstructured_store()