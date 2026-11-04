#include "../sp.h"
gboolean sp_benchmark;
int main(int argc,char **argv){
 if(argc!=3)return 2;
 asset_dir=g_strdup(argv[1]);
 if(!load_config(argv[2]))goto error;
 J *ws=windows_list(),*current=desktop_current();
 if(!ws||!current||json_object_array_length(ws)!=1)goto error;
 J *window=json_object_array_get_idx(ws,0);
 for(int i=0;i<3;i++)if(!desktop_action((const char*[]){"focus","close","move"}[i],window,current))goto error;
 puts(json_object_to_json_string(ws));puts(json_object_to_json_string(current));
 J *logout=logout_argv();puts(json_object_to_json_string(logout));json_object_put(logout);
 json_object_put(ws);json_object_put(current);return 0;
 error:g_printerr("%s\n",last_error?last_error:"Invalid backend response");return 2;
}
