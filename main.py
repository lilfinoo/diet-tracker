import openai
from dotenv import load_dotenv
import os
import sys

# DON'T CHANGE THIS !!!
# Garante que o diretório pai seja adicionado ao sys.path para importações relativas
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask, send_from_directory, g, session
from flask_cors import CORS
from flask_migrate import Migrate
from sqlalchemy import text

# Importa todos os modelos para que o Flask-SQLAlchemy os reconheça
from src.models.user import db, User, DietEntry, Measurement, UserProfile, ChatMessage, WorkoutPlan, WorkoutExercise, DietPlan, DietPlanMeal

from src.routes.user_routes import user_bp

load_dotenv()

app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), 'copilot'))
app.config['SECRET_KEY'] = 'asdf#FGSgvasgf$5$WGT' # Use uma chave secreta forte e única

# Configuração CORS
# Permite credenciais (cookies, headers de autorização) e define as origens permitidas.
# Para produção, substitua '*' por domínios específicos (ex: 'http://localhost:3000' ).
CORS(app, supports_credentials=True, origins=['*'])

# Configuração de sessão
app.config['SESSION_COOKIE_SECURE'] = False  # True em produção (requer HTTPS)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax' # 'Strict' para maior segurança, 'Lax' para compatibilidade

# Registra o Blueprint das rotas de usuário
app.register_blueprint(user_bp, url_prefix='/api')

# Database configuration - PostgreSQL
# Pega a URL do banco de dados da variável de ambiente DATABASE_URL
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "postgresql://postgres:buchagamer@db.ojhamkcppsvmrimlgfuz.supabase.co:5432/postgres")

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False # Desabilita o rastreamento de modificações de objetos para economizar memória
db.init_app(app)

# Configurar Flask-Migrate
migrate = Migrate(app, db)

# Configura a chave da API OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Cria todas as tabelas do banco de dados se elas não existirem
# Isso é útil para o primeiro setup, mas em produção use Flask-Migrate
with app.app_context():
    db.create_all()

# Hook para definir a variável de sessão do PostgreSQL antes de cada requisição
# Isso é usado para o Row-Level Security (RLS) se você o tiver configurado no seu banco de dados
@app.before_request
def set_rls_user_id():
    if "user_id" in session:
        # Define a variável de sessão do PostgreSQL para o usuário logado
        # Converte para string para evitar problemas de tipo no SQL
        db.session.execute(text("SET app.user_id = :user_id"), {"user_id": str(session["user_id"])})
        db.session.commit()
    else:
        # Se não houver usuário logado, defina a variável como NULL ou um valor que não corresponda a um user_id
        # Isso garante que usuários não logados não vejam dados (se RLS estiver ativo)
        db.session.execute(text("SET app.user_id = :user_id"), {"user_id": ""}) # Ou 'NULL' se seu RLS espera NULL
        db.session.commit()

# Rota para servir o painel administrativo (admin.html)
@app.route('/admin')
def serve_admin():
    static_folder_path = app.static_folder
    admin_path = os.path.join(static_folder_path, 'admin.html')
    if os.path.exists(admin_path):
        return send_from_directory(static_folder_path, 'admin.html')
    else:
        return "admin.html not found", 404
    
# Rota catch-all para servir arquivos estáticos e o index.html para rotas SPA
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    static_folder_path = app.static_folder
    if static_folder_path is None:
            return "Static folder not configured", 404

    # Tenta servir o arquivo solicitado diretamente
    if path != "" and os.path.exists(os.path.join(static_folder_path, path)):
        return send_from_directory(static_folder_path, path)
    else:
        # Se o arquivo não for encontrado, serve o index.html (para Single Page Applications)
        index_path = os.path.join(static_folder_path, 'index.html')
        if os.path.exists(index_path):
            return send_from_directory(static_folder_path, 'index.html')
        else:
            return "index.html not found", 404

if __name__ == '__main__':
   # Executa o aplicativo Flask
   # host='0.0.0.0' torna o servidor acessível externamente (útil em contêineres/VMs)
   # port=8081 define a porta
   # debug=True ativa o modo de depuração (NÃO USE EM PRODUÇÃO)
   app.run(host='0.0.0.0', port=8081, debug=True)
