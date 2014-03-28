<h4>
    Dropbox
</h4>

<style>
    .dropbox-confirm-selection {
        padding-top: 10px;
    }
    .dropbox-confirm-dlg {
        display: inline-block;
    }
    .dropbox-folder-picker {
        margin-top: 10px;
    }
</style>

<div id="dropboxScope" class="scripted">
    <!-- <pre data-bind="text: ko.toJSON($data, null, 2)"></pre> -->

    <!-- Settings Pane -->
    <div class="dropbox-settings" data-bind='if: showSettings'>
        <div class="well well-sm">
            <span class="authorized-by">
                Authorized by <a data-bind="attr: {href: urls.owner}">
                    {{ownerName}}
                </a>
            </span>
            <span data-bind="visible: userHasAuth">
                <a data-bind="click: deauthorize"
                    class="text-danger pull-right">Deauthorize</a>
            </span>
        </div><!-- end well -->
        <div class="row">
            <div class="col-md-12">
                <p><strong>Shared Folder:</strong></p>
                    <h4 class="selected-folder">
                        <i class="icon-folder-close-alt"></i>
                        <a data-bind="attr: {href: urls.files}"class='selected-folder-name'>
                            {{folderName}}
                        </a>
                    </h4>
                <button data-bind="click: togglePicker,
                                    css: {active: showPicker}"
                        class="btn btn-default">Change</button>

                <!-- Folder picker -->
                <div data-bind="if: showPicker">
                    <div id="myGrid"
                         class="filebrowser hgrid dropbox-folder-picker"></div>
                </div>

                <!-- Queued selection -->
                <div class="dropbox-confirm-selection"
                    data-bind="if: selected">
                    <form data-bind="submit: submitSettings">

                        <h4 class="dropbox-confirm-dlg">
                            Share &ldquo;{{ selectedFolderName }}&rdquo;?
                        </h4>
                        <div class="pull-right">
                            <button class="btn btn-default"
                                    data-bind="click: cancelSelection">Cancel</button>
                            <input type="submit"
                                    class="btn btn-primary"
                                    value="Submit">

                        </div>
                    </form>
                </div>

            </div><!-- end col -->
        </div><!-- end row -->
    </div><!-- end .dropbox-settings -->

     <!-- Import Access Token Button -->
    <div data-bind="if: showImport">
        <a data-bind="click: importAuth" href="#" class="btn btn-primary">
            Authorize: Import Access Token from Profile
        </a>
    </div>

    <!-- Oauth Start Button -->
    <div data-bind="if: showTokenCreateButton">
        <a data-bind="attr: {href: urls.auth}" class="btn btn-primary">
            Authorize: Create Access Token
        </a>
    </div>

    <!-- Flashed Messages -->
    <div class="help-block">
        <p data-bind="html: message, attr: {class: messageClass}"></p>
    </div>
</div><!-- end #dropboxScope -->


<script>
    $script(['/static/addons/dropbox/dropboxConfigManager.js']);
    $script.ready('dropboxConfigManager', function() {
        var url = '${node["api_url"] + "dropbox/config/"}';
        var dropbox = new DropboxConfigManager('#dropboxScope', url, '#myGrid');
    });
</script>
