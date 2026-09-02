from dataclasses import asdict

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from app.api.auth_dependencies import get_auth_service, require_trusted_origin, require_user
from app.auth.service import AuthError
from app.config import get_settings

router = APIRouter(prefix='/api/auth', tags=['auth'])
SESSION_COOKIE = 'creativeops_session'
FLOW_COOKIE = 'creativeops_oauth_flow'
CALLBACK_PATH = '/api/auth/google/callback'


def cookie(response, name, value='', *, delete=False):
    path = CALLBACK_PATH if name == FLOW_COOKIE else '/'
    options = dict(path=path, secure=get_settings().auth_cookie_secure, httponly=True, samesite='lax')
    if delete:
        response.delete_cookie(name, **options)
    else:
        response.set_cookie(name, value, max_age=600 if name == FLOW_COOKIE else 604800, **options)


@router.get('/google/start')
async def google_start(request: Request, service=Depends(get_auth_service)):
    try:
        result = await service.begin_google_login(request.query_params.get('return_to', '/'))
        response = RedirectResponse(result.location, status_code=307, headers={'Cache-Control': 'no-store'})
        cookie(response, FLOW_COOKIE, result.flow_secret)
        return response
    except AuthError as error:
        return JSONResponse({'detail': error.code}, status_code=503, headers={'Cache-Control': 'no-store'})


@router.get('/google/callback')
async def google_callback(request: Request, service=Depends(get_auth_service)):
    origin = get_settings().auth_frontend_origin.rstrip('/')
    try:
        query = request.query_params
        code = query.get('code') if len(query.getlist('code')) <= 1 and len(query.getlist('state')) <= 1 else None
        result = await service.complete_google_login(request.cookies.get(FLOW_COOKIE, ''),
                    query.get('state', ''), code, provider_error=query.get('error'))
        response = RedirectResponse(origin + result.return_to, status_code=303)
        cookie(response, SESSION_COOKIE, result.session_secret)
    except AuthError as error:
        response = RedirectResponse(origin + '/?auth_error=' + error.code, status_code=303)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    cookie(response, FLOW_COOKIE, delete=True)
    return response


@router.get('/me')
async def me(user=Depends(require_user)):
    profile = asdict(user)
    profile['id'] = str(profile['id'])
    return JSONResponse(profile, headers={'Cache-Control': 'no-store'})


@router.post('/logout', dependencies=[Depends(require_trusted_origin)])
async def logout(request: Request, service=Depends(get_auth_service)):
    try:
        await service.logout(request.cookies.get(SESSION_COOKIE))
        response = Response(status_code=204)
    except AuthError as error:
        response = JSONResponse({'detail': error.code}, status_code=503)
    cookie(response, SESSION_COOKIE, delete=True)
    response.headers['Cache-Control'] = 'no-store'
    return response
