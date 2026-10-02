package com.agripredict.app;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.provider.MediaStore;
import android.webkit.*;
import androidx.core.content.FileProvider;
import java.io.File;
import java.io.IOException;

/** Host-restricted HTTPS client. Farmer photos are sent only to the configured AgriPredict server. */
public class MainActivity extends Activity {
    private WebView web;
    private ValueCallback<Uri[]> upload;
    private Uri cameraUri;
    private static final int FILE_REQUEST=10;
    private String allowedHost;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        allowedHost=Uri.parse(BuildConfig.APP_URL).getHost();
        web=new WebView(this);setContentView(web);
        WebSettings settings=web.getSettings();settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);settings.setAllowFileAccess(false);settings.setAllowContentAccess(true);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        CookieManager.getInstance().setAcceptCookie(true);
        web.setWebViewClient(new WebViewClient(){
            @Override public boolean shouldOverrideUrlLoading(WebView view,WebResourceRequest request){
                Uri uri=request.getUrl();
                if("https".equals(uri.getScheme()) && allowedHost.equals(uri.getHost()))return false;
                if("https".equals(uri.getScheme()))startActivity(new Intent(Intent.ACTION_VIEW,uri));
                return true;
            }
            @Override public void onReceivedSslError(WebView view,android.webkit.SslErrorHandler handler,android.net.http.SslError error){handler.cancel();}
        });
        web.setWebChromeClient(new WebChromeClient(){
            @Override public boolean onShowFileChooser(WebView view,ValueCallback<Uri[]> callback,FileChooserParams params){
                if(upload!=null)upload.onReceiveValue(null);
                upload=callback;cameraUri=null;
                Intent pick=new Intent(Intent.ACTION_GET_CONTENT);pick.setType("image/*");pick.addCategory(Intent.CATEGORY_OPENABLE);
                Intent chooser=Intent.createChooser(pick,"Choose a leaf photo");
                Intent camera=new Intent(MediaStore.ACTION_IMAGE_CAPTURE);
                try {
                    File folder=new File(getCacheDir(),"photos");folder.mkdirs();
                    File photo=File.createTempFile("leaf-",".jpg",folder);
                    cameraUri=FileProvider.getUriForFile(MainActivity.this,getPackageName()+".files",photo);
                    camera.putExtra(MediaStore.EXTRA_OUTPUT,cameraUri);
                    camera.addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION|Intent.FLAG_GRANT_READ_URI_PERMISSION);
                    chooser.putExtra(Intent.EXTRA_INITIAL_INTENTS,new Intent[]{camera});
                } catch(IOException ignored) {cameraUri=null;}
                startActivityForResult(chooser,FILE_REQUEST);return true;
            }
        });
        if(state!=null)web.restoreState(state);else web.loadUrl(BuildConfig.APP_URL+"/crop-intelligence");
    }
    @Override protected void onActivityResult(int request,int result,Intent data){
        super.onActivityResult(request,result,data);
        if(request==FILE_REQUEST && upload!=null){
            Uri[] uris=null;
            if(result==RESULT_OK){if(data!=null && data.getData()!=null)uris=new Uri[]{data.getData()};else if(cameraUri!=null)uris=new Uri[]{cameraUri};}
            upload.onReceiveValue(uris);upload=null;cameraUri=null;
        }
    }
    @Override protected void onSaveInstanceState(Bundle state){super.onSaveInstanceState(state);web.saveState(state);}
    @Override public void onBackPressed(){if(web.canGoBack())web.goBack();else super.onBackPressed();}
    @Override protected void onDestroy(){if(upload!=null)upload.onReceiveValue(null);web.destroy();super.onDestroy();}
}
