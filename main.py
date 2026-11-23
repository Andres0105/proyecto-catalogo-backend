import os
import requests
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List

import models
import schemas
import agent
from database import engine, get_db

# Crea la tabla en Supabase automáticamente si aún no existe
models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="API de Catálogo de Productos",
    version="1.0.0",
    description="Servicio Backend conectado a PostgreSQL en Supabase"
)

# Habilitar CORS para permitir llamadas desde Vercel o desarrollo local
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # En producción puedes acotarlo al dominio de Vercel
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1. Obtener todos los productos
@app.get("/api/v1/products", response_model=List[schemas.ProductResponse], tags=["Productos"])
def list_products(db: Session = Depends(get_db)):
    return db.query(models.Product).all()

# 2. Registrar un nuevo producto (con integración opcional de Webhook de Slack - Paso 3.2)
@app.post("/api/v1/products", response_model=schemas.ProductResponse, status_code=status.HTTP_201_CREATED, tags=["Productos"])
def create_product(product: schemas.ProductCreate, db: Session = Depends(get_db)):
    nuevo_producto = models.Product(**product.model_dump())
    db.add(nuevo_producto)
    db.commit()
    db.refresh(nuevo_producto)

    # Paso 3.2: Integración con Slack (Herramienta 2)
    slack_webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if slack_webhook_url:
        try:
            requests.post(
                slack_webhook_url,
                json={"text": f"🚀 ¡Nuevo producto registrado en el inventario!: *{nuevo_producto.name}* - Precio: ${nuevo_producto.price} (Stock: {nuevo_producto.stock})"},
                timeout=3
            )
        except Exception as e:
            print("Error enviando alerta a Slack:", e)

    return nuevo_producto

# 3. Agente de IA para Consultas en Lenguaje Natural a la Base de Datos
@app.post("/api/v1/agent/query", response_model=schemas.AgentQueryResponse, tags=["Agente IA"])
def ask_ai_agent(request: schemas.AgentQueryRequest, db: Session = Depends(get_db)):
    answer, products, sql = agent.query_database_agent(request.query, db)
    return schemas.AgentQueryResponse(
        answer=answer,
        matched_products=products,
        sql_action=sql
    )
