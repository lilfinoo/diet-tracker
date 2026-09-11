import pytest


@pytest.mark.parametrize("path", ["/", "/app/hoje", "/app/progresso/atividades"])
def test_spa_paths_return_the_application_shell(client, path):
    response = client.get(path)

    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert 'id="mainScreen"' in response.get_data(as_text=True)


@pytest.mark.parametrize(
    ("path", "mimetype"),
    [
        ("/styles.css", "text/css"),
        ("/script.js", "text/javascript"),
        ("/minha-pasta/alimentos.json", "application/json"),
    ],
)
def test_physical_static_files_are_served_directly(client, path, mimetype):
    response = client.get(path)

    assert response.status_code == 200
    assert response.mimetype == mimetype
    assert 'id="mainScreen"' not in response.get_data(as_text=True)


def test_unknown_api_path_never_falls_back_to_the_spa(client):
    response = client.get("/api/unknown-route")

    assert response.status_code == 404
    assert 'id="mainScreen"' not in response.get_data(as_text=True)


def test_spa_shell_uses_root_absolute_application_assets(client):
    source = client.get("/app/progresso/atividades").get_data(as_text=True)

    for asset in (
        'href="/styles.css?',
        'href="/fluid.css?',
        'src="/fluid.js?',
        'src="/script.js?',
        'src="/js/plans.js?',
        'src="/assets/logoIsolada.png"',
    ):
        assert asset in source

    exercise_image = client.get("/assets/exercises/wger/wger-573.png")
    assert exercise_image.status_code == 200
    assert exercise_image.mimetype == "image/png"


def test_frontend_exposes_history_navigation_adapter(client):
    source = client.get("/script.js").get_data(as_text=True)

    assert "const VIEW_PATHS" in source
    assert "pushState" in source
    assert "replaceState" in source
    assert "window.addEventListener('popstate'" in source


def test_application_shell_exposes_five_primary_destinations(client):
    source = client.get("/app/hoje").get_data(as_text=True)

    assert source.count('class="nav-btn') == 5
    for view in ("diet", "diet_plans", "workout_plans", "progress", "stats"):
        assert f'data-app-view="{view}"' in source
    assert 'id="progressTab"' in source
    assert 'aria-label="Seções de progresso"' not in source
    assert 'id="personalRecordsTab"' in source
    assert "showTab('personalRecords')" in source
    assert source.count("onclick=\"showTab('progress')\"") >= 4
    profile = source.split('id="statsTab"', 1)[1].split('id="professionalTab"', 1)[0]
    assert "showTab('measurements')" not in profile
    assert "showTab('activities')" not in profile
    assert "showTab('achievements')" not in profile

    diet = source.split('id="diet_plansTab"', 1)[1].split('id="workout_plansTab"', 1)[0]
    assert 'id="dietDailyDate"' in diet
    assert 'id="dietDailyMacros"' in diet
    assert 'id="dietDailyMealsBody"' in diet
    assert 'id="dietDailyPlan"' in diet
    assert 'id="dietCurrentPlanBody"' not in diet
    assert 'id="dietTableBody"' not in diet
    assert 'fab--diet-plans' not in diet
    today = source.split('id="dietTab"', 1)[1].split('id="diet_plansTab"', 1)[0]
    assert 'id="todayCardapioBody"' in today
    assert 'id="todayRecentMeals"' not in today
    assert "editDailyNutritionTargets()" not in today
    workout = source.split('id="workout_plansTab"', 1)[1].split('id="chatTab"', 1)[0]
    assert 'id="workoutPlanHub"' in workout
    assert 'id="workoutPlansLibrary" class="workout-plans-library hidden"' in workout
    assert 'id="workoutPlansLibraryTitle" tabindex="-1">Meus planos' in workout
    assert 'fab--workout-plans' not in workout
    plans_script = client.get("/js/plans.js").get_data(as_text=True)
    assert 'class="workout-hub-details"' in plans_script
    assert "Mostrar detalhes" in plans_script
    assert "adaptar ou gerar um novo treino" not in source
    assert 'id="profileUpgradePill"' not in source
    assert source.count('onclick="closeViewDietPlanModal()"') == 1
    assert source.count('onclick="closeViewWorkoutPlanModal()"') == 1
    assert "onclick=\"showTab('chat')\"" not in today
    assert "returnFromAssistant()" in source
    assert "Limpar tela" in source
    script = client.get("/script.js").get_data(as_text=True)
    assert "if (!currentUser || !currentUser.is_premium) return;" in script
    assert "async function loadChatHistory()" in script
    assert 'id="chatSendButton"' in source
    assert "if (isSendingChat) return;" in script
    assert "setChatPending(false);" in script
    assert "async function readAuthResponse(response)" in script
    assert "O servidor não conseguiu concluir a solicitação" in script
    assert 'id="billingPaymentModal"' in source
    assert "PIX libera 30 dias" in script
    assert "confirmBillingCheckout('pix')" in source
    assert 'id="professionalDrafts"' in source
    professional = client.get("/js/professional.js").get_data(as_text=True)
    assert "Rascunhos para revisar" in source
    assert "Tentar novamente" in professional
    assert 'id="routeStatus"' in source
    assert "VIEW_LABELS" in script
    assert "Compartilhar ${esc(plan.title)} no WhatsApp" in professional

    plans = client.get("/js/plans.js").get_data(as_text=True)
    assert 'data-meal-checkin' not in plans
    assert 'data-diet-day-complete' not in plans


@pytest.mark.parametrize(
    "path",
    ["/admin", "/admin/", "/admin.html", "/copilot/admin.html"],
)
def test_admin_page_aliases_are_hidden_from_guests(client, path):
    assert client.get(path).status_code == 404
