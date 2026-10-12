/* Display-free GTK3 stylesheet parser; does not initialize GTK or start Wofi. */
#include <gtk/gtk.h>
#include <stdio.h>

static void on_error(GtkCssProvider *provider, GtkCssSection *section,
                     GError *error, gpointer data) {
    (void)provider;
    (void)section;
    ++*(int *)data;
    fprintf(stderr, "GTK CSS parsing error: %s\n", error->message);
}

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    int errors = 0;
    GError *load_error = NULL;
    GtkCssProvider *provider = gtk_css_provider_new();
    g_signal_connect(provider, "parsing-error", G_CALLBACK(on_error), &errors);
    gboolean loaded = gtk_css_provider_load_from_path(provider, argv[1], &load_error);
    if (load_error) {
        fprintf(stderr, "GTK CSS load error: %s\n", load_error->message);
        g_clear_error(&load_error);
    }
    g_object_unref(provider);
    return loaded && errors == 0 ? 0 : 1;
}
