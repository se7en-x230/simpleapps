#define _GNU_SOURCE
#include "auth.h"
#include <security/pam_appl.h>
#include <stdlib.h>
#include <string.h>
/* The same password-only conversation used by conventional desktop lockers.
 * An unsupported conversation fails closed; PAM controls delays and lockouts. */
struct credentials {const char *user, *password;};
static int conversation(int n,const struct pam_message **messages,struct pam_response **out,void *data) {
  if(n<=0 || n>PAM_MAX_NUM_MSG)return PAM_CONV_ERR;
  struct credentials *c=data;struct pam_response *r=calloc((size_t)n,sizeof(*r));
  if(!r)return PAM_BUF_ERR;
  for(int i=0;i<n;i++) {
    switch(messages[i]->msg_style) {
      case PAM_PROMPT_ECHO_OFF:r[i].resp=strdup(c->password);break;
      case PAM_PROMPT_ECHO_ON:r[i].resp=strdup(c->user);break;
      case PAM_ERROR_MSG:case PAM_TEXT_INFO:continue;
      default:goto error;
    }
    if(!r[i].resp)goto error;
  }
  *out=r;return PAM_SUCCESS;
error:
  for(int i=0;i<n;i++)if(r[i].resp){explicit_bzero(r[i].resp,strlen(r[i].resp));free(r[i].resp);}
  free(r);return PAM_CONV_ERR;
}
int authenticate(const char *service,const char *user,const char *password) {
  struct credentials credentials={user,password};
  struct pam_conv conv={conversation,&credentials};pam_handle_t *handle=NULL;
#ifdef SIMPLELOCK_TEST
  /* Test builds only. Production cannot redirect PAM's trusted config directory. */
  const char *dir=getenv("SIMPLELOCK_TEST_PAM_DIR");
  if(!dir)return PAM_SYSTEM_ERR;
  int result=pam_start_confdir(service,user,&conv,dir,&handle);
#else
  int result=pam_start(service,user,&conv,&handle);
#endif
  if(result==PAM_SUCCESS)result=pam_authenticate(handle,PAM_DISALLOW_NULL_AUTHTOK);
  if(handle)pam_end(handle,result);
  return result;
}
