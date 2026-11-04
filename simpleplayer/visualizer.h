/* Cava's raw output, rendered only while this player window is open. */
#include <glib-unix.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <signal.h>
#include <sys/wait.h>
static GtkWidget *visualizer;
static GPid cava_pid;
static int cava_fd=-1;
static guint cava_watch;
static char *cava_config;
static guint8 bars[64],pending[64];
static guint pending_size;
static void cava_draw(GtkDrawingArea *area,cairo_t *cr,int width,int height,gpointer unused) {
    (void)unused;GdkRGBA color;gtk_widget_get_color(GTK_WIDGET(area),&color);
    cairo_pattern_t *gradient=cairo_pattern_create_linear(0,height,0,0);
    cairo_pattern_add_color_stop_rgba(gradient,0,color.red,color.green,color.blue,.35);
    cairo_pattern_add_color_stop_rgba(gradient,1,color.red,color.green,color.blue,1);
    cairo_set_source(cr,gradient);double step=(double)width/64;
    for(int i=0;i<64;i++){double h=MAX(2.,bars[i]/255.*(height-2));cairo_rectangle(cr,i*step,height-h,MAX(1.,step-2),h);cairo_fill(cr);}
    cairo_pattern_destroy(gradient);
}
static gboolean cava_read(int fd,GIOCondition condition,gpointer unused) {
    (void)unused;guint8 buffer[4096];ssize_t n;
    while((n=read(fd,buffer,sizeof buffer))>0)for(ssize_t i=0;i<n;i++){
        pending[pending_size++]=buffer[i];if(pending_size==64){memcpy(bars,pending,64);pending_size=0;}}
    gtk_widget_queue_draw(visualizer);
    if(n==0||(n<0&&errno!=EAGAIN&&errno!=EINTR)||(condition&(G_IO_HUP|G_IO_ERR))){cava_watch=0;return G_SOURCE_REMOVE;}
    return G_SOURCE_CONTINUE;
}
static void cava_start(void) {
    char *program=g_find_program_in_path("cava");if(!program)return;
    int fd=g_file_open_tmp("simpleplayer-cava-XXXXXX",&cava_config,NULL);if(fd<0){g_free(program);return;}close(fd);
    const char *config="[general]\nbars=64\nframerate=30\nautosens=1\n[input]\nmethod=pulse\nsource=auto\n[output]\nmethod=raw\nraw_target=/dev/stdout\ndata_format=binary\nbit_format=8bit\nchannels=mono\n";
    char *argv[]={program,"-p",cava_config,NULL};
    if(g_file_set_contents(cava_config,config,-1,NULL)&&g_spawn_async_with_pipes(NULL,argv,NULL,G_SPAWN_DO_NOT_REAP_CHILD|G_SPAWN_STDERR_TO_DEV_NULL,NULL,NULL,&cava_pid,NULL,&cava_fd,NULL,NULL)){
        fcntl(cava_fd,F_SETFL,fcntl(cava_fd,F_GETFL)|O_NONBLOCK);cava_watch=g_unix_fd_add(cava_fd,G_IO_IN|G_IO_HUP|G_IO_ERR,cava_read,NULL);}
    g_free(program);
}
static void cava_stop(void){
    if(cava_watch)g_source_remove(cava_watch);
    if(cava_fd>=0)close(cava_fd);
    if(cava_pid){kill(cava_pid,SIGKILL);while(waitpid(cava_pid,NULL,0)<0&&errno==EINTR){}g_spawn_close_pid(cava_pid);}
    if(cava_config){unlink(cava_config);g_free(cava_config);}
}
