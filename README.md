# fiche_aidmsportnew
# Générateur de Fiches Produits – Nouvelle version

Ce dépôt propose une refonte complète de l'outil de génération de fiches produits permettant de créer des pages produit structurées à partir d'un code **EAN** ou d'une référence **SKU**.  
L'objectif est de fournir aux e‑commerçants un flux de travail simple et automatisé pour passer d'un identifiant produit à une fiche produit cohérente, rédigée en français et prête à être importée dans **PrestaShop**.

## Fonctionnalités principales

* **Recherche par EAN ou SKU** : le service expose une route `/api/search` qui accepte un champ `ean` ou `sku`.  
  - Pour un EAN, l'outil tente d'interroger des bases de données publiques (au besoin la route peut être adaptée pour intégrer un service tiers tel que [Icecat](https://icecat.biz/en/) ou [EAN‑DB](https://ean-db.com/)).  
  - À défaut de données externes, l'application retourne une fiche générique indiquant que le produit n'a pas été trouvé, avec des champs vides.  
  - Le code est conçu pour être modulaire afin de brancher facilement d'autres API.
* **Génération de description en français** : afin de proposer un descriptif soigné, la fonction `generate_french_description` traduit les descriptions anglaises via le module `deep_translator` (qui s’appuie sur l’API non‑authentifiée de Google Traduction) et formate un texte marketing fluide en français. En absence de description anglaise, l’outil construit une phrase générique à partir du nom et de la catégorie.
* **Sauvegarde et consultation des produits** : les produits trouvés sont stockés en mémoire dans une liste Python (`products_db`) et peuvent être consultés via la route `/api/products`. Cette base peut facilement être remplacée par une persistance en base de données (SQLite, PostgreSQL…).
* **Export CSV pour PrestaShop** : la route `/api/export/{product_id}` génère un fichier CSV compatible avec l’importation de catalogue PrestaShop. Les colonnes (nom, prix, description, SKU/EAN, catégorie, image, etc.) suivent la structure attendue par PrestaShop.  
  Un bouton d’export est également disponible sur l’interface web.
* **Interface web conviviale** : grâce à Jinja2, la page d’accueil (`/`) fournit un formulaire de recherche et affiche la fiche produit générée avec un style épuré. Le texte est lisible, structuré et met en valeur les caractéristiques du produit.  
  Cette interface facilite la validation visuelle avant import dans PrestaShop.
* **Prêt pour l’intégration PrestaShop** : bien que la création directe de produits via l’API PrestaShop nécessite une clef API et l’URL du back‑office, le code contient une fonction d’exemple (`create_product_in_prestashop`) pour illustrer comment appeler l’API REST PrestaShop avec des identifiants fournis par l’utilisateur.

## Démarrage rapide

1. **Installation des dépendances :**

   ```bash
   cd fiche_aidmsport
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Lancement du serveur :**

   ```bash
   uvicorn app.main:app --reload
   ```

   Le serveur sera accessible sur `http://127.0.0.1:8000`. Visitez cette adresse dans votre navigateur pour accéder à l’interface graphique.  
   La documentation API (Swagger UI) est disponible à `http://127.0.0.1:8000/docs`.

3. **Recherche d’un produit :**

   - Entrez un EAN ou un SKU valide dans le formulaire et cliquez sur « Rechercher ».
   - Si des informations externes sont disponibles, elles seront affichées ; sinon, une fiche générique sera proposée.
   - Utilisez le bouton « Exporter CSV » pour générer un fichier compatible PrestaShop.

## Configuration de l’intégration PrestaShop

L’API PrestaShop utilise une authentification de type **Basic** où la clef API est passée comme nom d’utilisateur et le mot de passe est laissé vide.  
Pour permettre la création automatisée de produits, renseignez les variables d’environnement suivantes avant de lancer le serveur :

```bash
export PRESTASHOP_BASE_URL="https://votre-boutique.example.com"
export PRESTASHOP_API_KEY="CLEF_API"
```

Vous pourrez alors appeler la fonction `create_product_in_prestashop()` dans le code (ou exposer une route dédiée) pour envoyer les fiches directement à votre boutique.

## Limitations et améliorations possibles

* **Source de données externe** : sans API publique pour traduire un EAN/SKU en informations produit, l’outil retourne une fiche générique. En vous inscrivant à un service (Icecat, EAN‑DB, Go‑UPC…), il suffit de modifier la fonction `lookup_product` dans `app/main.py` pour interroger ce service.
* **Persistance** : la base de données en mémoire est volatile. Pour un usage en production, remplacez-la par un stockage durable (Base de données, fichier JSON, etc.).
* **Génération avancée de descriptions** : avec une clef OpenAI ou un autre LLM, vous pourriez créer des descriptions plus riches et adaptées au SEO.

Ce projet se veut une base fonctionnelle et extensible pour automatiser la création de fiches produits. N’hésitez pas à l’adapter à vos besoins et à l’améliorer !
