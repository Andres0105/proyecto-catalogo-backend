import os
import re
import json
import urllib.request
from typing import List, Dict, Any, Tuple
from sqlalchemy.orm import Session
import models

def query_database_agent(query_text: str, db: Session) -> Tuple[str, List[models.Product], str]:
    """
    Agente de Inteligencia Artificial que interpreta lenguaje natural,
    realiza consultas sobre la base de datos PostgreSQL en Supabase y retorna
    una respuesta explicativa junto con los productos coincidentes y la consulta SQL ejecutada.
    """
    clean_q = query_text.lower().strip()
    gemini_key = os.getenv("GEMINI_API_KEY")
    all_products = db.query(models.Product).all()

    # Si hay clave de Gemini API disponible, usamos el LLM para razonamiento avanzado
    if gemini_key:
        try:
            products_summary = [
                {"id": p.id, "name": p.name, "price": p.price, "stock": p.stock, "image_url": p.image_url}
                for p in all_products
            ]
            prompt = f"""
            Eres el Asistente Inteligente del Catálogo de Productos conectado a una base de datos PostgreSQL en Supabase.
            Los productos actuales en la base de datos son:
            {json.dumps(products_summary, ensure_ascii=False)}

            El usuario pregunta: "{query_text}"

            Instrucciones:
            1. Responde de forma cordial, concisa y precisa en español.
            2. Menciona precios, stock o detalles relevantes según lo solicitado.
            3. Si el usuario pregunta por productos específicos, incluye sus IDs en el array 'matched_ids'.
            4. Proporciona una sentencia SQL hipotética o real que represente la consulta en el campo 'sql_query'.

            Devuelve tu respuesta ÚNICAMENTE en formato JSON válido con esta estructura:
            {{
                "answer": "tu respuesta explicativa aquí",
                "matched_ids": [1, 2],
                "sql_query": "SELECT * FROM products WHERE ..."
            }}
            """
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
            req_data = json.dumps({
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"response_mime_type": "application/json"}
            }).encode('utf-8')
            req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                result = json.loads(resp.read().decode('utf-8'))
                raw_text = result["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(raw_text)
                matched_ids = parsed.get("matched_ids", [])
                matched_prods = [p for p in all_products if p.id in matched_ids]
                return parsed.get("answer", ""), matched_prods, parsed.get("sql_query", "SELECT * FROM products")
        except Exception as e:
            print(f"Gemini API fallback to internal agent: {e}")

    # Motor Inteligente Determinista Integrado (funciona 100% autónomo sin claves externas)
    if not all_products:
        return "Actualmente no hay productos registrados en la base de datos de Supabase.", [], "SELECT * FROM products;"

    # 1. Producto más caro / costoso
    if any(w in clean_q for w in ["más caro", "mas caro", "mayor precio", "más costoso", "mas costoso"]):
        prod = max(all_products, key=lambda p: p.price)
        sql = "SELECT * FROM products ORDER BY price DESC LIMIT 1;"
        answer = f"El producto más caro en el inventario es **{prod.name}** con un precio de **${prod.price:,.2f}** (Stock: {prod.stock} unidades)."
        return answer, [prod], sql

    # 2. Producto más barato / económico
    if any(w in clean_q for w in ["más barato", "mas barato", "menor precio", "más económico", "mas economico", "accesible"]):
        prod = min(all_products, key=lambda p: p.price)
        sql = "SELECT * FROM products ORDER BY price ASC LIMIT 1;"
        answer = f"El producto más económico es **{prod.name}**, con un precio de solo **${prod.price:,.2f}** (Stock: {prod.stock} unidades)."
        return answer, [prod], sql

    # 3. Consultas de filtro por precio (menor a, mayor a)
    num_match = re.search(r'(\d+[\.,]?\d*)', clean_q)
    if num_match and any(w in clean_q for w in ["menor", "menos de", "bajo", "hasta", "máximo", "maximo"]):
        val = float(num_match.group(1).replace(',', '.'))
        matched = [p for p in all_products if p.price <= val]
        sql = f"SELECT * FROM products WHERE price <= {val};"
        if matched:
            answer = f"Encontré **{len(matched)}** producto(s) con precio menor o igual a **${val:,.2f}**:"
        else:
            answer = f"No encontré ningún producto con precio menor o igual a **${val:,.2f}**."
        return answer, matched, sql

    if num_match and any(w in clean_q for w in ["mayor", "más de", "mas de", "sobre", "mínimo", "minimo"]):
        val = float(num_match.group(1).replace(',', '.'))
        matched = [p for p in all_products if p.price >= val]
        sql = f"SELECT * FROM products WHERE price >= {val};"
        if matched:
            answer = f"Encontré **{len(matched)}** producto(s) con precio mayor o igual a **${val:,.2f}**:"
        else:
            answer = f"No encontré productos con precio mayor a **${val:,.2f}**."
        return answer, matched, sql

    # 4. Stock / Unidades / Inventario
    if any(w in clean_q for w in ["stock", "unidades", "disponibles", "cantidad", "cuanto queda", "cuánto queda"]):
        total_stock = sum(p.stock for p in all_products)
        total_valor = sum(p.price * p.stock for p in all_products)
        sql = "SELECT SUM(stock) as total_stock, SUM(price * stock) as valor_total FROM products;"
        answer = f"El inventario cuenta con un total de **{total_stock} unidades** distribuidas en **{len(all_products)} productos**. El valor total del catálogo es de **${total_valor:,.2f}**."
        return answer, all_products, sql

    # 5. Búsqueda por término específico (ej: laptop, celular, etc.)
    matched = [p for p in all_products if p.name.lower() in clean_q or any(term in p.name.lower() for term in clean_q.split() if len(term) > 3)]
    if matched:
        sql = f"SELECT * FROM products WHERE LOWER(name) LIKE '%...%';"
        answer = f"Encontré **{len(matched)}** coincidencia(s) para tu búsqueda en la base de datos:"
        return answer, matched, sql

    # 6. Saludos o consulta general / catálogo
    sql = "SELECT * FROM products ORDER BY id DESC;"
    total_val = sum(p.price * p.stock for p in all_products)
    answer = (
        f"¡Hola! Soy tu Agente de IA para el inventario de Supabase. "
        f"Actualmente hay **{len(all_products)} productos** registrados en la base de datos con un valor total de **${total_val:,.2f}**. "
        f"Puedes preguntarme sobre precios (ej: *¿Cuál es el más barato?*), disponibilidad (ej: *¿Hay laptops en stock?*) o rangos de precios (ej: *Productos de menos de $1500*)."
    )
    return answer, all_products, sql
