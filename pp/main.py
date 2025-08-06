"""FastAPI application for generating product sheets from EAN or SKU codes.

This module exposes a simple REST API and a minimal HTML interface to search for
product information by EAN or SKU, generate a French‑language product
description, display a rich product card and export the result as a
PrestaShop‑compatible CSV. The design is intentionally modular so that you can
plug in your own data sources (e.g. Icecat, EAN‑DB) or language models for
generating descriptions.

Usage::

    uvicorn app.main:app --reload

The app will be available at http://localhost:8000. A Swagger UI is provided
under /docs.
"""

from __future__ import annotations

import csv
import os
import uuid
from io import StringIO
from typing import List, Optional, Dict, Any

import requests
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from deep_translator import GoogleTranslator

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# Base URL and API key for PrestaShop integration can be set via environment
# variables. If not set, the create_product_in_prestashop function will raise.

PRESTASHOP_BASE_URL: Optional[str] = os.environ.get("PRESTASHOP_BASE_URL")
PRESTASHOP_API_KEY: Optional[str] = os.environ.get("PRESTASHOP_API_KEY")

# Template loader
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

# FastAPI app
app = FastAPI(title="Générateur Fiches Produits", version="2.1.0")


class SearchRequest(BaseModel):
    """Payload for the /api/search endpoint.

    Either `ean` or `sku` must be provided. Both are optional strings; if none
    are given an exception is raised.
    """

    ean: Optional[str] = Field(None, description="Code EAN (13 chiffres)")
    sku: Optional[str] = Field(None, description="Référence SKU du produit")


class Product(BaseModel):
    """Dataclass representing a product stored in the in‑memory database."""

    id: str
    ean: Optional[str] = None
    sku: Optional[str] = None
    name: str
    brand: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    original_price: Optional[float] = None
    description: str
    features: Optional[List[str]] = None
    image: Optional[str] = None
    material: Optional[str] = None
    type: Optional[str] = None
    search_type: str
    search_term: str
    created_at: str

    def to_prestashop_row(self) -> Dict[str, Any]:
        """Return a dictionary corresponding to a single row in a PrestaShop CSV.

        The exact column names can be adapted depending on your PrestaShop
        configuration. Here we follow the basic structure: name, price,
        description, reference (SKU), EAN, category, image URL.
        """
        return {
            "Name": self.name,
            "Price": self.price or "",
            "Description": self.description,
            "Reference": self.sku or "",
            "EAN": self.ean or "",
            "Category": self.category or "",
            "ImageURL": self.image or "",
            "Brand": self.brand or "",
        }


class ProductDatabase:
    """Simple in‑memory product store.

    Stores products in a list. In a production system you would likely
    substitute this with a database or another persistence layer.
    """

    def __init__(self) -> None:
        self._products: List[Product] = []

    def add(self, product: Product) -> None:
        self._products.append(product)

    def get_all(self) -> List[Product]:
        return list(self._products)

    def get_by_id(self, product_id: str) -> Optional[Product]:
        for prod in self._products:
            if prod.id == product_id:
                return prod
        return None


products_db = ProductDatabase()


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def lookup_product_by_ean(ean: str) -> Dict[str, Any]:
    """Lookup product information by EAN.

    This function can be customised to call external services such as Icecat,
    EAN‑DB or Go‑UPC. Currently it returns an empty dict to signal that no
    reliable data source is available. You can register for these services and
    then update this function accordingly.
    """
    # Example: call EAN‑DB (requires API key). This stub returns empty.
    # If implementing, set EAN_DB_API_KEY as env var and perform a GET request.
    # See README for details.
    return {}


def lookup_product_by_sku(sku: str) -> Dict[str, Any]:
    """Lookup product information by SKU.

    Without a public SKU database, we return an empty dict. For a real
    implementation you might integrate with your own PIM or ERP to fetch
    product details by SKU.
    """
    return {}


def generate_french_description(
    name: str, brand: Optional[str], category: Optional[str], features: Optional[List[str]], english_desc: Optional[str]
) -> str:
    """Generate a French description from provided fields.

    The function concatenates a marketing sentence based on available fields
    (name, brand, category) and, if provided, translates the English description
    to French using Google Translate via deep_translator. It silently catches
    translation errors and falls back to the original English text when
    necessary.
    """
    parts: List[str] = []
    # Phrase d'accroche
    if name:
        if brand:
            parts.append(f"Découvrez {name} de la marque {brand}.")
        else:
            parts.append(f"Découvrez {name}.")
    if category:
        parts.append(f"Il s'agit d'un(e) {category.lower()}.")
    # Ajouter les caractéristiques sous forme de phrases
    if features:
        # Construire une phrase à partir des caractéristiques
        features_fr = []
        for feat in features:
            # essayer de traduire chaque caractéristique
            try:
                features_fr.append(GoogleTranslator(source="en", target="fr").translate(feat))
            except Exception:
                features_fr.append(feat)
        parts.append("Caractéristiques principales : " + "; ".join(features_fr) + ".")
    # Traduire la description anglaise si présente
    if english_desc:
        try:
            translation = GoogleTranslator(source="en", target="fr").translate(english_desc)
            parts.append(translation)
        except Exception:
            # si la traduction échoue, utiliser le texte original
            parts.append(english_desc)
    # Assurer que la description se termine par un point
    description = " ".join(parts)
    if not description.endswith("."):
        description += "."
    return description


def create_product_in_prestashop(product: Product) -> None:
    """Create a product in PrestaShop using its Webservice API.

    This function demonstrates how to send a basic POST request to the
    PrestaShop API to create a product. It requires that
    `PRESTASHOP_BASE_URL` and `PRESTASHOP_API_KEY` are configured. See the
    README for details on enabling the Webservice API in your shop.

    Raises:
        RuntimeError: if the configuration variables are missing.
        HTTPException: if the API call fails.
    """
    if not PRESTASHOP_BASE_URL or not PRESTASHOP_API_KEY:
        raise RuntimeError(
            "PRESTASHOP_BASE_URL et PRESTASHOP_API_KEY doivent être définis pour créer un produit dans PrestaShop."
        )
    # Construct payload for PrestaShop; uses XML as required by PrestaShop API.
    # Here we build a minimal product with name, price, reference and active flag.
    # For complex products (combinations, images, features) the XML structure
    # becomes more detailed.
    product_xml = f"""
    <prestashop xmlns:xlink="http://www.w3.org/1999/xlink">
      <product>
        <active>1</active>
        <name>
          <language id="1">{product.name}</language>
        </name>
        <price>{product.price or 0}</price>
        <reference>{product.sku or ''}</reference>
        <ean13>{product.ean or ''}</ean13>
        <description>
          <language id="1">{product.description}</language>
        </description>
        <id_category_default>2</id_category_default>
        <associations>
          <categories>
            <category>
              <id>2</id>
            </category>
          </categories>
        </associations>
      </product>
    </prestashop>
    """.strip()

    url = f"{PRESTASHOP_BASE_URL}/api/products"
    try:
        response = requests.post(
            url,
            data=product_xml.encode("utf-8"),
            headers={"Content-Type": "application/xml", "Accept": "application/xml"},
            auth=(PRESTASHOP_API_KEY, ""),
            timeout=10,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'appel à PrestaShop : {exc}")
    if response.status_code not in (200, 201):
        raise HTTPException(status_code=response.status_code, detail=f"Erreur API PrestaShop: {response.text}")


def perform_product_lookup(search_req: SearchRequest) -> Dict[str, Any]:
    """Aggregate lookup functions to fetch product data.

    Returns a dictionary with keys: name, brand, category, price, original_price,
    description (english), features, image, material, type.

    You can modify this function to call external services when an EAN or SKU
    is provided. For now, it returns an empty dict and is handled in
    `search_product`.
    """
    if search_req.ean:
        return lookup_product_by_ean(search_req.ean)
    if search_req.sku:
        return lookup_product_by_sku(search_req.sku)
    return {}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    """Render the home page with the search form and list of existing products."""
    return templates.TemplateResponse(
        "index.html", {"request": request, "products": products_db.get_all()}
    )


@app.post("/api/search", response_class=JSONResponse)
def search_product(payload: SearchRequest) -> JSONResponse:
    """Search for a product by EAN or SKU and store it in the database.

    The function calls `perform_product_lookup` to retrieve product details.
    If no information is found, it returns a generic template using the
    provided code.
    """
    # Validate payload
    if not payload.ean and not payload.sku:
        raise HTTPException(status_code=400, detail="Veuillez fournir un code EAN ou une référence SKU.")

    lookup_data = perform_product_lookup(payload)
    # Determine search type and term
    search_term = payload.ean or payload.sku or ""
    search_type = "EAN" if payload.ean else "SKU"

    # If lookup_data is empty, create generic fields
    name = lookup_data.get("name") or (
        f"Produit {search_type} {search_term}" if search_term else "Produit inconnu"
    )
    brand = lookup_data.get("brand") or None
    category = lookup_data.get("category") or None
    price = lookup_data.get("price") or None
    original_price = lookup_data.get("original_price") or None
    english_desc = lookup_data.get("description") or None
    features = lookup_data.get("features") or None
    image = lookup_data.get("image") or None
    material = lookup_data.get("material") or None
    prod_type = lookup_data.get("type") or None

    # Generate French description
    description_fr = generate_french_description(name, brand, category, features, english_desc)

    product = Product(
        id=str(uuid.uuid4()),
        ean=payload.ean,
        sku=payload.sku,
        name=name,
        brand=brand,
        category=category,
        price=price,
        original_price=original_price,
        description=description_fr,
        features=features,
        image=image,
        material=material,
        type=prod_type,
        search_type=search_type,
        search_term=search_term,
        created_at=str(
            __import__("datetime").datetime.now().isoformat(timespec="seconds")
        ),
    )

    # Save to in‑memory database
    products_db.add(product)

    return JSONResponse(content={"success": True, "product": product.dict()})


@app.get("/api/products", response_class=JSONResponse)
def get_products() -> JSONResponse:
    """Return the list of all stored products."""
    return JSONResponse(content={"success": True, "products": [p.dict() for p in products_db.get_all()]})


@app.get("/api/export/{product_id}", response_class=Response)
def export_prestashop_csv(product_id: str) -> Response:
    """Export a single product as a CSV row compatible with PrestaShop.

    Returns a CSV file for download. If the product is not found, raises
    HTTPException.
    """
    product = products_db.get_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Produit non trouvé")
    csv_buffer = StringIO()
    writer = csv.DictWriter(csv_buffer, fieldnames=list(product.to_prestashop_row().keys()), delimiter=';')
    writer.writeheader()
    writer.writerow(product.to_prestashop_row())
    csv_data = csv_buffer.getvalue()
    csv_buffer.close()
    filename = f"fiche_{product.id}.csv"
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/api/health", response_class=JSONResponse)
def health_check() -> JSONResponse:
    """Simple health check endpoint."""
    return JSONResponse(content={"status": "OK", "products_count": len(products_db.get_all())})
  
