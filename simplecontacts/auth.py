from pathlib import Path
import sys
import core
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'simple-common'))
from google_oauth import authorize

def connect(client_path=None):
 client,token=authorize(core.SCOPE,client_path)
 value={'token':token['access_token'],'refresh_token':token['refresh_token'],'token_uri':'https://oauth2.googleapis.com/token','client_id':client['client_id'],'client_secret':client['client_secret'],'scopes':[core.SCOPE]}
 from google.oauth2.credentials import Credentials
 from google.auth.transport.requests import AuthorizedSession
 session=AuthorizedSession(Credentials.from_authorized_user_info(value))
 core.request(session,'GET','people/me/connections',params={'personFields':core.FIELDS,'pageSize':1,'sources':'READ_SOURCE_TYPE_CONTACT'})
 with core.locked():core.write(core.ROOT/'google-token.json',value)
 core.sync();return True
