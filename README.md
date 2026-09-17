# Food Analyzer - AI Engineering Final Project

Bu layihə **AI Academy - Software Engineering Final Project (Bahar 2026)** çərçivəsində "Topic 2" olaraq hazırlanmışdır. Proqram təminatı qida məlumatlarının təhlili üçün təqdim olunmuş süni intellekt modulunu (`ai/` paketi) əhatə edən tam funksional, CLI və Docker dəstəkli arxitekturadan ibarətdir.

## 🚀 Əsas Xüsusiyyətlər

* **Qorunan AI Modulu:** Təqdim edilmiş `ai/` paketi heç bir dəyişiklik edilmədən sistemə inteqrasiya olunmuşdur.
* **CLI İnterfeysi:** Əmrlər sətri (Command Line Interface) vasitəsilə rahat və sürətli idarəetmə.
* **Storage Repository:** Məlumatların saxlanması və oxunması üçün modulyar "Repository" pattern tətbiqi.
* **Təhlükəsiz Konfiqurasiya:** API açarları və mühit dəyişənləri `.env` faylı vasitəsilə təhlükəsiz şəkildə idarə olunur.
* **Konteynerləşdirmə:** İzolə olunmuş mühitdə problemsiz işləməsi üçün tam Docker dəstəyi.
* **Testləşdirmə:** Təqdim olunmuş "smoke test"lər (tüstü testləri) və əlavə proqram təminatı testləri.

## 📂 Qovluq Strukturu

```text
Food_Analyzer/
├── src/                    # Əsas tətbiq kodları (api, cli, services, storage, config)
├── static/                 # Layihənin statik faylları
├── tests/                  # Unit, integration və tələb olunan AI "smoke" testləri
├── .env.example            # Nümunə konfiqurasiya faylı (GitHub-a gedən format)
├── .gitignore              # Git tərəfindən izlənməyən faylların siyahısı (məs. .env)
├── docker-compose.yml      # Konteyner idarəetməsi və orkestrasiyası
├── Dockerfile              # Proqramın Docker imicinin konfiqurasiyası
├── requirements.txt        # Python paket asılılıqlarının siyahısı
├── demo_ai.py              # AI modulunu API olmadan yoxlamaq üçün test skripti
├── pytest.ini              # Test mühitinin (Pytest) konfiqurasiyası
├── TOPIC.md                # Mövzu və tapşırıq haqqında ümumi təlimatlar
└── README.md               # Layihənin əsas sənədləşdirməsi