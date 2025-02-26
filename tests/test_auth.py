import pytest, os
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse
from jose import JWTError
from fastapi import HTTPException

from  main import app
from  constants import errorMessages
from  model import userModel
from  utils import security, dotenv, send_mail, enumeration
from  database.database import get_db, engine, Base

valid_user_active_admin = {"name": "Forsen", "email": "valid@email.com", "connection": "PROFESSOR", "password": "123456"}
valid_user_active_user = {"name": "Guy Beahm", "email": "valid2@email.com", "connection": "ESTUDANTE", "password": "123456"}
duplicated_user = {"name": "John", "email": "valid@email.com", "connection": "ESTUDANTE", "password": "123456"} 
valid_user_not_active = {"name": "Peter", "email": "valid3@email.com", "connection": "ESTUDANTE", "password": "123456"}
valid_user_to_be_deleted = {"name": "Simon", "email": "valid4@email.com", "connection": "ESTUDANTE", "password": "123456"}
invalid_connection = {"name": "Mike", "email": "invalid@email.com", "connection": "INVALID", "password": "123456"}
invalid_pass_length = {"name": "Victor", "email": "invalid@email.com", "connection": "SERVIDOR", "password": "123"}
invalid_pass = {"name": "Luisa", "email": "invalid@email.com", "connection": "SERVIDOR", "password": "123abc"}
valid_social_user = { "name": "Paulo Kogos", "email": "kogos@email.com" }

total_registed_users = 5

client = TestClient(app)

class TestAuth:
  __admin_access_token__ = None
  __admin_refresh_token__ = None
  __user_access_token__ = None
  __user_refresh_token__ = None
  
  @pytest.fixture(scope="session", autouse=True)
  def setup(self, session_mocker):
    session_mocker.patch('utils.security.generate_six_digit_number_code', return_value=123456)
    session_mocker.patch('utils.send_mail.send_verification_code', return_value=JSONResponse(status_code=200, content={ "status": "success" }))
    session_mocker.patch('utils.send_mail.send_reset_password_code', return_value=JSONResponse(status_code=200, content={ "status": "success" }))
  
    # /register - ok
    response = client.post("/api/auth/register", json=valid_user_active_admin)
    data = response.json()
    assert response.status_code == 201
    assert data['status'] == 'success'
    
    response = client.post("/api/auth/register", json=valid_user_active_user)
    data = response.json()
    assert response.status_code == 201
    assert data['status'] == 'success'
    
    response = client.post("/api/auth/register", json=valid_user_not_active)
    data = response.json()
    assert response.status_code == 201
    assert data['status'] == 'success'
    
    response = client.post("/api/auth/register", json=valid_user_to_be_deleted)
    data = response.json()
    assert response.status_code == 201
    assert data['status'] == 'success'
    
    # /activate-account: ok 
    response = client.patch("/api/auth/activate-account", json={"email": valid_user_active_admin['email'], "code": 123456})
    data = response.json()
    assert response.status_code == 200
    assert data['status'] == 'success'
    
    response = client.patch("/api/auth/activate-account", json={"email": valid_user_active_user['email'], "code": 123456})
    data = response.json()
    assert response.status_code == 200
    assert data['status'] == 'success'

    # /login: ok
    response = client.post("/api/auth/login", json={"email": valid_user_active_admin['email'], "password": valid_user_active_admin['password']})
    data = response.json()
    assert response.status_code == 200
    assert data['token_type'] == 'bearer'
    assert security.verify_token(data['access_token'])['email'] == valid_user_active_admin['email']
    
    TestAuth.__admin_access_token__ = data['access_token']
    TestAuth.__admin_refresh_token__ = data['access_token']
    
    response = client.post("/api/auth/login", json={"email": valid_user_active_user['email'], "password": valid_user_active_user['password']})
    data = response.json()
    assert response.status_code == 200
    assert data['token_type'] == 'bearer'
    assert security.verify_token(data['access_token'])['email'] == valid_user_active_user['email']
    
    TestAuth.__user_access_token__ = data['access_token']
    TestAuth.__user_refresh_token__ = data['access_token']

    # login social - criação conta (nova)
    response = client.post('/api/auth/login/social', json=valid_social_user)
    data = response.json()
    assert response.status_code == 200
    assert data["access_token"] != None
    assert data["token_type"] == "bearer"
    assert data["is_new_user"] == True

    # Atualiza role do active_user_admin de USER para ADMIN
    with engine.connect() as connection:
      query = "UPDATE users SET role = 'ADMIN' WHERE id = 1;"
      connection.execute(text(query))
      connection.commit()
      
    yield
  
    userModel.Base.metadata.drop_all(bind=engine)

  # REGISTER
  def test_auth_register_connection_invalid(self, setup):
    response = client.post("/api/auth/register", json=invalid_connection)
    data = response.json()
    assert response.status_code == 400
    assert data['detail'] == errorMessages.INVALID_CONNECTION

  def test_auth_register_password_invalid_length(self, setup):
    response = client.post("/api/auth/register", json=invalid_pass_length)
    data = response.json()
    assert response.status_code == 400
    assert data['detail'] == errorMessages.INVALID_PASSWORD

  def test_auth_register_password_invalid_characters(self, setup):
    response = client.post("/api/auth/register", json=invalid_pass)
    data = response.json()
    assert response.status_code == 400
    assert data['detail'] == errorMessages.INVALID_PASSWORD

  def test_auth_register_duplicate_email(self, setup):
    response = client.post("/api/auth/register", json=duplicated_user)
    data = response.json()
    assert response.status_code == 400
    assert data['detail'] == errorMessages.EMAIL_ALREADY_REGISTERED

  # LOGIN
  def test_auth_login_wrong_password(self, setup):
    response = client.post("/api/auth/login", json={ "email": valid_user_active_admin['email'], "password": "PASSWORD" })
    data = response.json()
    assert response.status_code == 404
    assert data['detail'] == errorMessages.PASSWORD_NO_MATCH

  def test_auth_login_not_found(self, setup):
    response = client.post("/api/auth/login", json=invalid_connection)
    data = response.json()
    assert response.status_code == 404
    assert data['detail'] == errorMessages.USER_NOT_FOUND

  def test_auth_login_not_active(self, setup):
    # /login - nao ativo
    response = client.post("/api/auth/login", json={"email": valid_user_not_active['email'], "password": valid_user_not_active['password']})
    data = response.json()
    assert response.status_code == 401
    assert data['detail'] == errorMessages.ACCOUNT_IS_NOT_ACTIVE

  def test_auth_login_social(self, setup):
    response = client.post('/api/auth/login/social', json=valid_social_user)
    data = response.json()
    assert response.status_code == 200
    assert data["access_token"] != None
    assert data["refresh_token"] != None
    assert data["token_type"] == "bearer"
    assert data["is_new_user"] == False

  # RESEND CODE
  def test_auth_resend_code_user_not_found(self, setup):
    response = client.post("/api/auth/resend-code", json={"email": invalid_connection['email']})
    data = response.json()
    assert response.status_code == 404
    assert data['detail'] == errorMessages.USER_NOT_FOUND
    
  def test_auth_resend_code_already_active(self, setup):
    response = client.post("/api/auth/resend-code", json={"email": valid_user_active_admin['email']})
    data = response.json()
    assert response.status_code == 400
    assert data['status'] == 'error'
    assert data['message'] == errorMessages.ACCOUNT_ALREADY_ACTIVE

  def test_auth_resend_code_success(self, setup):
    response = client.post("/api/auth/resend-code", json={"email": valid_user_not_active['email']})
    data = response.json()
    assert response.status_code == 201
    assert data['status'] == 'success'

  # ACTIVATE ACCOUNT
  def test_auth_activate_account_user_not_found(self, setup):
    response = client.patch("/api/auth/activate-account", json={"email": invalid_connection['email'], "code": 123456})
    data = response.json()
    assert response.status_code == 404
    assert data['detail'] == errorMessages.USER_NOT_FOUND
  
  def test_auth_activate_account_already_active(self, setup):
    response = client.patch("/api/auth/activate-account", json={"email": valid_user_active_admin['email'], "code": 123456})
    data = response.json()
    assert response.status_code == 200
    assert data['status'] == 'error'
    assert data['message'] == errorMessages.ACCOUNT_ALREADY_ACTIVE
  
  def test_auth_activate_account_invalid_code(self, setup):
    response = client.patch("/api/auth/activate-account", json={"email": valid_user_not_active['email'], "code": 000000})
    data = response.json()
    assert response.status_code == 404
    assert data['detail'] == errorMessages.INVALID_CODE
    
  # RESET PASSWORD - REQUEST
  def test_auth_reset_password_request_user_not_found(self, setup):
    response = client.post("/api/auth/reset-password/request", json={"email": invalid_connection['email']})
    data = response.json()
    assert response.status_code == 404
    assert data['detail'] == errorMessages.USER_NOT_FOUND
    
  def test_auth_reset_password_request_not_active(self, setup):
    response = client.post("/api/auth/reset-password/request", json={"email": valid_user_not_active['email']})
    data = response.json()
    assert response.status_code == 404
    assert data['detail'] == errorMessages.ACCOUNT_IS_NOT_ACTIVE
    
  # RESET PASSWORD - VERIFY
  def test_auth_reset_password_verify_user_not_found(self, setup):
    response = client.post("/api/auth/reset-password/verify", json={"email": invalid_connection['email'], "code": 123456})
    data = response.json()
    assert response.status_code == 404
    assert data['detail'] == errorMessages.USER_NOT_FOUND
    
  # RESET PASSWORD - CHANGE
  def test_auth_reset_password_change_user_not_found(self, setup):
    response = client.patch("/api/auth/reset-password/change", json={"email": invalid_connection['email'], "password": "123456", "code": 123456})
    data = response.json()
    assert response.status_code == 404
    assert data['detail'] == errorMessages.USER_NOT_FOUND
    
  def test_auth_reset_password_change_invalid_password(self, setup):
    # Senha inválida
    response = client.patch("/api/auth/reset-password/change", json={"email": valid_user_active_admin['email'], "password": "ABC", "code": 123456})
    data = response.json()
    assert response.status_code == 400
    assert data['detail'] == errorMessages.INVALID_PASSWORD

  # RESET PASSWORD - Fluxo de troca
  def test_auth_reset_password_flow(self, setup):
    response = client.post("/api/auth/reset-password/verify", json={"email": valid_user_active_admin['email'], "code": 123456})
    data = response.json()
    assert response.status_code == 404
    assert data['detail'] == errorMessages.NO_RESET_PASSWORD_CODE
    
    # Requisitar troca de senha
    response = client.post("/api/auth/reset-password/request", json={"email": valid_user_active_admin['email']})
    data = response.json()
    assert response.status_code == 200
    assert data['status'] == 'success'
    
    # Solicitação inválido
    response = client.patch("/api/auth/reset-password/change", json={"email": valid_user_not_active['email'], "password": "123456", "code": 123456})
    data = response.json()
    assert response.status_code == 401
    assert data['detail'] == errorMessages.INVALID_REQUEST
    
    # Código inválido - verify
    response = client.post("/api/auth/reset-password/verify", json={"email": valid_user_active_admin['email'], "code": 000000})
    data = response.json()
    assert response.status_code == 400
    assert data['detail'] == errorMessages.INVALID_RESET_PASSWORD_CODE
    
    # Código inválido - change
    response = client.patch("/api/auth/reset-password/change", json={"email": valid_user_active_admin['email'], "password": "123456", "code": 000000})
    data = response.json()
    assert response.status_code == 400
    assert data['detail'] == errorMessages.INVALID_RESET_PASSWORD_CODE
    
    # Código válido
    response = client.post("/api/auth/reset-password/verify", json={"email": valid_user_active_admin['email'], "code": 123456})
    data = response.json()
    assert response.status_code == 200
    assert data['status'] == 'success'
    
    # Troca de senha
    response = client.patch("/api/auth/reset-password/change", json={"email": valid_user_active_admin['email'], "password": "123456", "code": 123456})
    data = response.json()
    assert response.status_code == 200
    assert data['name'] == valid_user_active_admin['name']
    assert data['connection'] == valid_user_active_admin['connection']
    assert data['email'] == valid_user_active_admin['email']
    assert data['is_active'] == True
    
  def test_auth_connection_list(self, setup):
    response = client.get('/api/auth/vinculo')
    data = response.json()
    assert response.status_code == 200
    assert len(data) == 6
    
  def test_auth_refresh_token(self, setup):
    headers={'Authorization': f'Bearer {self.__admin_refresh_token__}'}
    response = client.post('/api/auth/refresh', json={}, headers=headers)
    data = response.json()
    assert response.status_code == 200    

  def test_root_request(self, setup):
    response = client.get('/')
    data = response.json()
    assert response.status_code == 200
    assert data['message'] == 'UnB-TV!'
  
  def test_security_generate_six_digit_number_code(self, setup):
    for _ in range(3):
      number = security.generate_six_digit_number_code()
      assert 100000 <= number <= 999999
      
  def test_security_verify_token_invalid_token(self, setup):
    with pytest.raises(HTTPException) as exc_info:
      security.verify_token("invalid_token")

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == errorMessages.INVALID_TOKEN
    
  def test_utils_validate_dotenv(self, setup):
    environment_secret_value = os.environ['SECRET']
    del os.environ['SECRET']
    
    with pytest.raises(EnvironmentError) as exc_info:
      dotenv.validate_dotenv()
      
    assert str(exc_info.value) == "SOME ENVIRONMENT VALUES WERE NOT DEFINED (missing: SECRET)"
    
    os.environ["SECRET"] = environment_secret_value

  @pytest.mark.asyncio
  async def test_auth_send_mail_send_verification_code_success(self, setup):
    send_mail.fm.config.SUPPRESS_SEND = 1
    with send_mail.fm.record_messages() as outbox:
      response = await send_mail.send_verification_code(valid_user_active_admin['email'], 123456)
      
      assert response.status_code == 200
      assert len(outbox) == 1
      assert outbox[0]['from'] == f'UNB TV <{os.environ["MAIL_FROM"]}>'  
      assert outbox[0]['To'] == valid_user_active_admin['email']
        
  @pytest.mark.asyncio
  async def test_auth_send_reset_password_code_success(self, setup):
    send_mail.fm.config.SUPPRESS_SEND = 1
    with send_mail.fm.record_messages() as outbox:
      response = await send_mail.send_reset_password_code(valid_user_active_admin['email'], 123456)
      
      assert response.status_code == 200
      assert len(outbox) == 1
      assert outbox[0]['from'] == f'UNB TV <{os.environ["MAIL_FROM"]}>'  
      assert outbox[0]['To'] == valid_user_active_admin['email']