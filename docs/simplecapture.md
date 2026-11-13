# Simplecapture

Screenshots, annotation and optional screen recording.

![simplecapture screenshot](screenshots/simplecapture.png)

```sh
./install --install simplecapture
simplecapture --menu
./install --uninstall simplecapture
```

See [features, configuration, dependencies and keyboard controls](../simplecapture/README.md).


For integration with Simpleslideshow, `simplecapture --region --edit --save --no-copy --print-path` captures and annotates a title image, then prints its saved filename. Cancellation prints no filename.

To annotate an existing image, use `simplecapture --input image.jpg --save --no-copy --print-path`. FFmpeg converts it to PNG for Swappy; the saved annotated copy has a unique filename and the original is not modified. Simpleslideshow uses this mode for its Title image action. Save (Ctrl+S) returns the annotated copy; closing without saving cancels.
