# OM4A — Ressources de modélisation du système électrique sénégalais

Ce dépôt rassemble les données d'entrée, configurations, résultats et scripts de post-traitement produits dans le cadre d'OpenMod4Africa (OM4A) pour le Sénégal. Il met en regard **GENeSYS-MOD**, **openTEPES** et **plan4res**, ainsi qu'un jeu de données de profils historiques régionaux de demande électrique.

> **Important :** il s'agit d'un dépôt de ressources et de résultats. Il ne contient pas les moteurs complets des trois modèles ni un environnement permettant de reproduire toutes les optimisations après clonage.

## Contenu

```text
.
├── GENeSYS-MOD/
│   ├── dataset/inputs_data/          # classeurs d'entrée Sénégal
│   ├── dataset/Results/              # résultats BAU, ID et NZ
│   └── scripts/                      # fusion de sorties sous Windows
├── openTEPES/
│   ├── SN2022/                       # cas détaillé 2022
│   └── SN2030/                       # cas 2030 et diagnostics spatiaux
├── plan4res/SN_ID_2030/
│   ├── TimeSeries/                   # demande et disponibilités horaires
│   ├── settings/                     # configuration et couplage GENeSYS-MOD
│   ├── csv_optim/ et csv_simul/      # entrées optimisation/simulation
│   ├── nc4_optim/ et nc4_simul/      # blocs NetCDF4
│   ├── results_optim/                # résultats d'investissement
│   └── results_simul/                # résultats opérationnels
└── Historical_Regional_Electricity_Demand_Profiles/
    ├── reconstruction_historical_load_senegal_2000_2022.ipynb
    ├── temperature_senegal_2000_2024.xlsx
    └── consommation et profils régionaux
```

## Périmètre des modèles

### GENeSYS-MOD

Les entrées décrivent trois trajectoires :

- **BAU** — *Business As Usual* ;
- **ID** — scénario de développement intermédiaire couplé à plan4res ;
- **NZ** — trajectoire *Net Zero*.

`dataset/inputs_data/` contient les classeurs et séries horaires. `dataset/Results/BAU`, `ID` et `NZ` contiennent notamment capacités, productions, émissions, coûts, échanges et bilans énergétiques.

Le script Windows `GENeSYS-MOD/scripts/Merge_GENeSYS-MOD_simulation_Results.bat` concatène par type les CSV de son répertoire. Il conserve les en-têtes de chaque source ; un nettoyage peut être nécessaire.

### openTEPES

- `openTEPES/SN2022/` contient dictionnaires, paramètres, résultats de marché et réseau, indicateurs, journaux et visualisations HTML pour 2022.
- `openTEPES/SN2030/` regroupe le cas 2030, ses résultats et deux scripts Python de diagnostic spatial.

Convention : `oT_Data_*` désigne les entrées, `oT_Dict_*` les correspondances, `oT_Result_*` les résultats et `oT_Plot_*` les visualisations.

### plan4res — SN_ID_2030

Ce cas transpose le scénario GENeSYS-MOD **ID** vers une représentation opérationnelle régionale du Sénégal en 2030. Il distingue **Dakar**, **Diourbel**, **Thiès**, **LS**, **FKK**, **ZS** et **MTKK**.

| Code | Régions regroupées |
| --- | --- |
| LS | Louga, Saint-Louis |
| FKK | Fatick, Kaolack, Kaffrine |
| ZS | Ziguinchor, Sédhiou |
| MTKK | Matam, Tambacounda, Kolda, Kédougou |

`settings/settingsCreateInputPlan4res.yml` définit 16 scénarios météorologiques (2000 à 2015), les technologies, contraintes, unités et conversions. `settings/settingsLinkageGENeSYS.yml` décrit le passage de GENeSYS-MOD vers plan4res.

`results_simul/` organise demande, puissance active, production, réserves, stockage, coûts marginaux, échanges et défaillance. `capacity_stochastic.xlsx` et `generation_stochastic.xlsx` fournissent des synthèses.

### Profils historiques de demande

Le notebook `Historical_Regional_Electricity_Demand_Profiles/reconstruction_historical_load_senegal_2000_2022.ipynb` documente la reconstruction et la régionalisation de la demande. Les classeurs voisins réunissent consommation, température et profils horaires.

## Scripts de post-traitement

Créer au besoin un environnement Python :

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install pandas numpy matplotlib plotly pyyaml openpyxl \
  geopandas shapely adjustText jupyter
```

Aucune version de dépendance n'est verrouillée.

### Échanges interrégionaux plan4res

```bash
python plan4res/SN_ID_2030/plot_interregional_exchanges_sn2030.py \
  plan4res/SN_ID_2030
```

Le script lit `results_simul/OUT/MeanImportExport.csv` et produit un résumé CSV et une carte SVG.

### Comparaison de l'hydroélectricité

```bash
python plan4res/SN_ID_2030/compare_hydro_large_genesys_plan4res_det_stoch.py \
  plan4res/SN_ID_2030
```

Ce script compare GENeSYS-MOD aux sorties plan4res déterministes et stochastiques. Fournir le répertoire du cas, car son chemin par défaut est propre à l'environnement Windows de l'auteur.

### Diagnostics spatiaux openTEPES

Les scripts de `openTEPES/SN2030/` utilisent GeoPandas, Shapely et Matplotlib. Contrôler leurs arguments et constantes : les sources géographiques et certains chemins dépendent de l'environnement d'origine.

## Formats

| Format | Usage |
| --- | --- |
| `.xlsx` | entrées, profils historiques et synthèses |
| `.csv` | entrées tabulaires et résultats |
| `.nc4` | blocs plan4res |
| `.yml` | configuration plan4res |
| `.html` | graphiques openTEPES |
| `.log` | journaux d'exécution |
| `.ipynb` | reconstruction de la demande |

## Précautions

- Plusieurs fichiers sont volumineux ; vérifier l'espace disque avant de les dupliquer.
- Les résultats dépendent des versions et paramètres consignés dans les configurations et journaux.
- Certains scripts conservent des chemins absolus historiques ; contrôler les arguments et constantes.
- Les unités diffèrent entre modèles. Les configurations plan4res documentent les conversions entre PJ, GWh, MWh, GW et MW.

## Citation et licence

Aucun fichier de licence ou de citation n'est fourni à la racine. Avant redistribution ou publication, contacter les responsables OM4A et citer les modèles et sources selon leurs conditions.
