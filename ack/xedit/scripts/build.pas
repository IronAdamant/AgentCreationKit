{
  AgentCreationKit (from Sandbox Room's builder): build or update plugins from a spec file (the SPEC parameter), one operation per line, fields
  separated by " | ". Lines starting with # are ignored. Safe to re-run: records and placed references are found
  by editor ID and only created when missing. The spec is the layout's source of truth: every run puts each
  reference where the spec says (a move made by hand in the Creation Kit must be copied into the spec).

    file     | NAME                          select the plugin to work on; created (ESL-flagged) if not loaded
    master   | NAME                          add a master to the current plugin
    header   | PATH | VALUE                  set a field of the current plugin's file header (CNAM author,
                                             SNAM description)
    copy     | SOURCE | NEW_EDID             copy a record (any loaded plugin) into the current plugin as new
    new      | SIG | NEW_EDID                create an empty record
    set      | EDID | PATH | VALUE           set a field by xEdit path, adding missing parts on the way
    remove   | EDID | PATH                   remove a field if present
    ref      | EDID | CELL | BASE | X Y Z | RX RY RZ | OPTS   place a reference, or update it to match: base,
                                             position and rotation. OPTS: "-" or any of persistent, scale=N,
                                             swap=TOKEN (material swap), radius=N (light radius override)
    prune    | CELL | PREFIX                 delete this plugin's refs in CELL whose editor IDs start with PREFIX
                                             and that no ref operation above placed (taken out of the spec)
    unref    | EDID | CELL                   delete a placed reference if it exists
    prunerecords | PREFIX                    delete this plugin's records (not references) whose editor IDs
                                             start with PREFIX and that no copy/new operation above made
    items    | EDID | TOKEN*COUNT ; ...      replace a container's inventory
    menuclear| EDID                          remove a terminal's menu items
    menu     | EDID | ID | TEXT | SUBMENU | CONDITION   append a terminal menu item. SUBMENU: a TERM, or "-" for
                                             an item that runs and redisplays the same menu.
                                             CONDITION: "-" or FUNCTION:PARAM:VALUE, run on the player
    script   | EDID | SCRIPTNAME             attach a script (once)
    propremove | EDID | SCRIPTNAME | NAME    drop a script property the script no longer has (if present)
    prop     | EDID | SCRIPTNAME | NAME | TYPE | VALUE   set a script property. TYPE Object, Int32, Float, Bool or
                                             "Array of Object" (VALUE: tokens separated by commas)

  Record tokens (SOURCE, BASE, values): @EDID (searched in every loaded plugin) or FILE:XXXXXX (an object ID in
  that file, e.g. Fallout4.esm:01F4A5). Anything else in a VALUE is used as is.
}
unit ACKBuild;

const
  TargetFile = '{{TARGET}}';
  OutDir = '{{OUT}}';
  SpecFile = '{{SPEC}}';
  MenuTemplate = 'VRWorkshopShared_VRTerminalConsoleTallOn';  // vanilla terminal whose menu items have conditions

var
  log, cache, refIdx, touched, made, built: TStringList;  // built: files selected by 'file' ops
  cur, refCell: IInterface;
  nErr, nOk: integer;

function Field(s: string; idx: integer): string;
var
  i, p: integer;
begin
  for i := 0 to idx - 1 do begin
    p := Pos(' | ', s);
    if p = 0 then begin
      Result := '';
      Exit;
    end;
    s := Copy(s, p + 3, Length(s));
  end;
  p := Pos(' | ', s);
  if p > 0 then
    s := Copy(s, 1, p - 1);
  Result := Trim(s);
end;

procedure Err(s: string);
begin
  log.Add('ERROR  ' + s);
  Inc(nErr);
end;

function FileByName(name: string): IInterface;
var
  i: integer;
begin
  Result := nil;
  for i := 0 to FileCount - 1 do
    if SameText(GetFileName(FileByIndex(i)), name) then
      Result := FileByIndex(i);
end;

// Depth-first search for a record by editor ID under a group. Interior cell blocks are always searched;
// the placed references under each cell only when refs is true (the game masters hold millions of them).
function FindInGroup(g: IInterface; edid: string; refs: boolean): IInterface;
var
  i: integer;
  e: IInterface;
begin
  Result := nil;
  for i := 0 to ElementCount(g) - 1 do begin
    e := ElementByIndex(g, i);
    if Signature(e) = 'GRUP' then begin
      if refs or (GroupType(e) = 2) or (GroupType(e) = 3) then
        Result := FindInGroup(e, edid, refs);
    end
    else if SameText(EditorID(e), edid) then
      Result := e;
    if Assigned(Result) then
      Exit;
  end;
end;

function FindInFile(f: IInterface; edid: string): IInterface;
var
  i: integer;
  g: IInterface;
begin
  Result := nil;
  for i := 0 to ElementCount(f) - 1 do begin
    g := ElementByIndex(f, i);
    if Signature(g) <> 'GRUP' then
      Continue;
    Result := MainRecordByEditorID(g, edid);
    if not Assigned(Result) and (Pos('CELL', Name(g)) > 0) then
      Result := FindInGroup(g, edid, SameText(ExtractFileExt(GetFileName(f)), '.esp'));
    if Assigned(Result) then
      Exit;
  end;
end;

// Winning record for an editor ID, searching the last loaded plugin first.
function FindAny(edid: string): IInterface;
var
  i: integer;
begin
  i := cache.IndexOf(edid);
  if i >= 0 then begin
    Result := ObjectToElement(cache.Objects[i]);
    Exit;
  end;
  Result := nil;
  for i := FileCount - 1 downto 0 do begin
    Result := FindInFile(FileByIndex(i), edid);
    if Assigned(Result) then begin
      cache.AddObject(edid, Result);
      Exit;
    end;
  end;
end;

function Remember(edid: string; r: IInterface): IInterface;
begin
  cache.AddObject(edid, r);
  Result := r;
end;

function Token(t: string): IInterface;
var
  p: integer;
  f: IInterface;
begin
  Result := nil;
  t := Trim(t);
  if Copy(t, 1, 1) = '@' then
    Result := FindAny(Copy(t, 2, Length(t)))
  else begin
    p := Pos(':', t);
    if p > 0 then begin
      f := FileByName(Copy(t, 1, p - 1));
      if Assigned(f) then
        Result := RecordByFormID(f, (GetLoadOrder(f) shl 24) or StrToInt('$' + Copy(t, p + 1, Length(t))), True);
    end;
  end;
  if not Assigned(Result) then
    Err('unknown record ' + t);
end;

// A value for SetEditValue: record tokens become load-order FormIDs.
function Value(v: string): string;
var
  r: IInterface;
begin
  Result := v;
  if (Copy(v, 1, 1) = '@') or ((Pos('.es', v) > 0) and (Pos(':', v) > 0)) then begin
    r := Token(v);
    if Assigned(r) then
      Result := IntToHex(GetLoadOrderFormID(r), 8);
  end;
end;

// Element at PATH, created part by part if missing.
function Ensure(e: IInterface; path: string): IInterface;
var
  p: integer;
  part: string;
  next: IInterface;
begin
  Result := e;
  while path <> '' do begin
    p := Pos('\', path);
    if p > 0 then begin
      part := Copy(path, 1, p - 1);
      path := Copy(path, p + 1, Length(path));
    end
    else begin
      part := path;
      path := '';
    end;
    next := ElementByPath(Result, part);
    if not Assigned(next) then
      next := Add(Result, part, True);
    if not Assigned(next) then begin
      Result := nil;
      Exit;
    end;
    Result := next;
  end;
end;

function Rec(edid: string): IInterface;
begin
  Result := FindAny(edid);
  if not Assigned(Result) then
    Err('record not found: ' + edid);
end;

// The current plugin's version of a record: itself if it lives there, else an override (created if missing).
function InCur(r: IInterface): IInterface;
var
  i: integer;
  m: IInterface;
begin
  if Equals(GetFile(r), cur) then begin
    Result := r;
    Exit;
  end;
  m := MasterOrSelf(r);
  for i := 0 to OverrideCount(m) - 1 do
    if Equals(GetFile(OverrideByIndex(m, i)), cur) then begin
      Result := OverrideByIndex(m, i);
      Exit;
    end;
  Result := wbCopyElementToFile(r, cur, False, False);
end;

procedure OpFile(name: string);
begin
  cur := FileByName(name);
  if not Assigned(cur) then begin
    cur := AddNewFileName(name, True);
    // IDs below 0x800 are reserved and an ESL must use 0x800-0xFFF: start there before adding records.
    SetElementNativeValues(ElementByIndex(cur, 0), 'HEDR\Next Object ID', $800);
    log.Add('created ' + name);
  end;
  if built.IndexOf(name) < 0 then
    built.Add(name);
  cache.Clear;
  refCell := nil;
end;

procedure OpCopy(src, edid: string);
var
  s, r: IInterface;
begin
  made.Add(edid);
  if Assigned(FindInFile(cur, edid)) then
    Exit;
  s := Token(src);
  if not Assigned(s) then
    Exit;
  r := wbCopyElementToFile(s, cur, True, Signature(s) <> 'CELL');
  SetEditorID(r, edid);
  Remember(edid, r);
  log.Add('copied ' + src + ' -> ' + edid);
end;

procedure OpNew(sig, edid: string);
var
  g, r: IInterface;
begin
  made.Add(edid);
  if Assigned(FindInFile(cur, edid)) then
    Exit;
  g := GroupBySignature(cur, sig);
  if not Assigned(g) then
    g := Add(cur, sig, True);
  r := Add(g, sig, True);
  SetEditorID(r, edid);
  Remember(edid, r);
  log.Add('new ' + sig + ' ' + edid);
end;

procedure OpSet(edid, path, v: string);
var
  r, e: IInterface;
begin
  r := Rec(edid);
  if not Assigned(r) then
    Exit;
  r := InCur(r);
  e := Ensure(r, path);
  if not Assigned(e) then begin
    Err('cannot create ' + edid + ' \ ' + path);
    Exit;
  end;
  v := StringReplace(v, '\n', #13#10, [rfReplaceAll]);  // the spec writes line breaks as \n

  SetEditValue(e, Value(v));
  // record links read back as 'EDID "Name" [SIG:ID]', so only check plain values
  if (Value(v) = v) and (GetEditValue(e) <> v) then
    log.Add('NOTE   ' + edid + ' \ ' + path + ' = "' + GetEditValue(e) + '" (asked "' + v + '")');
end;

procedure OpRemove(edid, path: string);
var
  r: IInterface;
begin
  r := Rec(edid);
  if Assigned(r) and Assigned(ElementByPath(r, path)) then
    RemoveElement(InCur(r), path);
end;

procedure SetXYZ(r: IInterface; path, xyz: string);
var
  sl: TStringList;
begin
  sl := TStringList.Create;
  sl.Delimiter := ' ';
  sl.DelimitedText := xyz;
  SetElementEditValues(r, path + '\X', sl[0]);
  SetElementEditValues(r, path + '\Y', sl[1]);
  SetElementEditValues(r, path + '\Z', sl[2]);
  sl.Free;
end;

// Placed references of the current plugin's version of one cell, by editor ID (built once per cell: searching
// the cell for every reference is quadratic and the room has well over a thousand of them).
procedure IndexGroup(g: IInterface);
var
  i: integer;
  e: IInterface;
begin
  for i := 0 to ElementCount(g) - 1 do begin
    e := ElementByIndex(g, i);
    if Signature(e) = 'GRUP' then
      IndexGroup(e)
    else if EditorID(e) <> '' then
      refIdx.AddObject(EditorID(e), e);
  end;
end;

procedure UseCell(cell: IInterface);
begin
  if Assigned(refCell) and Equals(refCell, cell) then
    Exit;
  refCell := cell;
  refIdx.Clear;
  touched.Clear;
  IndexGroup(ChildGroup(cell));
end;

// OPTS: "-" or space-separated persistent, scale=N, swap=TOKEN (material swap), radius=N (light radius)
function Opt(opts, key: string): string;
var
  sl: TStringList;
  i: integer;
begin
  Result := '';
  sl := TStringList.Create;
  sl.Delimiter := ' ';
  sl.StrictDelimiter := True;
  sl.DelimitedText := opts;
  for i := 0 to sl.Count - 1 do begin
    if sl[i] = key then
      Result := 'yes'
    else if Copy(sl[i], 1, Length(key) + 1) = key + '=' then
      Result := Copy(sl[i], Length(key) + 2, Length(sl[i]));
  end;
  sl.Free;
end;

procedure SetOrRemove(r: IInterface; path, v: string);
begin
  if v <> '' then
    SetElementEditValues(r, path, Value(v))
  else if Assigned(ElementByPath(r, path)) then
    RemoveElement(r, path);
end;

// Place a reference, or bring an existing one in line with the spec (base, position, rotation, options).
procedure OpRef(edid, cellId, base, pos, rot, opts: string);
var
  cell, b, r: IInterface;
  i: integer;
  before: string;
begin
  cell := Rec(cellId);
  b := Token(base);
  if not Assigned(cell) or not Assigned(b) then
    Exit;
  cell := InCur(cell);
  UseCell(cell);
  i := refIdx.IndexOf(edid);
  if i >= 0 then
    r := ObjectToElement(refIdx.Objects[i])
  else begin
    r := Add(cell, 'REFR', True);
    SetEditorID(r, edid);
    if Opt(opts, 'persistent') <> '' then
      SetIsPersistent(r, True);
    refIdx.AddObject(edid, r);
    log.Add('placed ' + edid);
  end;
  if (Opt(opts, 'persistent') <> '') and not GetIsPersistent(r) then
    SetIsPersistent(r, True);
  before := GetElementEditValues(r, 'NAME') + GetElementEditValues(r, 'DATA\Position\X') +
    GetElementEditValues(r, 'DATA\Position\Y') + GetElementEditValues(r, 'DATA\Rotation\Z');
  SetElementEditValues(r, 'NAME', IntToHex(GetLoadOrderFormID(b), 8));
  SetXYZ(r, 'DATA\Position', pos);
  SetXYZ(r, 'DATA\Rotation', rot);
  if (i >= 0) and (before <> GetElementEditValues(r, 'NAME') + GetElementEditValues(r, 'DATA\Position\X') +
    GetElementEditValues(r, 'DATA\Position\Y') + GetElementEditValues(r, 'DATA\Rotation\Z')) then
    log.Add('updated ' + edid);
  SetOrRemove(r, 'XSCL', Opt(opts, 'scale'));
  SetOrRemove(r, 'XMSP', Opt(opts, 'swap'));
  SetOrRemove(r, 'XRDS', Opt(opts, 'radius'));
  touched.Add(edid);
  Remember(edid, r);
end;

// Delete this plugin's references in the cell whose editor IDs start with PREFIX and were not placed by this
// run's ref operations (things taken out of the spec). Run it after the cell's last ref operation.
procedure OpPrune(cellId, prefix: string);
var
  cell, r: IInterface;
  i: integer;
begin
  cell := Rec(cellId);
  if not Assigned(cell) then
    Exit;
  UseCell(InCur(cell));
  for i := refIdx.Count - 1 downto 0 do
    if (Copy(refIdx[i], 1, Length(prefix)) = prefix) and (touched.IndexOf(refIdx[i]) < 0) then begin
      r := ObjectToElement(refIdx.Objects[i]);
      log.Add('removed ' + refIdx[i]);
      refIdx.Delete(i);
      Remove(r);
    end;
end;

// Records the spec no longer makes (a chest or terminal taken out of the layout). Run after the prune of the
// references that placed them.
procedure OpPruneRecords(prefix: string);
var
  i, k: integer;
  r: IInterface;
  sig, edid: string;
begin
  for i := RecordCount(cur) - 1 downto 0 do begin
    r := RecordByIndex(cur, i);
    if not (IsMaster(r) and Equals(GetFile(r), cur)) then
      Continue;
    sig := Signature(r);
    edid := EditorID(r);
    if (sig = 'REFR') or (sig = 'ACHR') or (sig = 'CELL') or (sig = 'NAVM') or (sig = 'WRLD') then
      Continue;
    if (Copy(edid, 1, Length(prefix)) <> prefix) or (made.IndexOf(edid) >= 0) then
      Continue;
    k := cache.IndexOf(edid);
    if k >= 0 then
      cache.Delete(k);
    log.Add('removed record ' + sig + ' ' + edid);
    Remove(r);
  end;
end;

procedure OpHeader(path, v: string);
var
  h, e: IInterface;
begin
  h := ElementByIndex(cur, 0);  // the file header (TES4)
  e := ElementByPath(h, path);
  if not Assigned(e) then
    e := Add(h, path, True);
  if not Assigned(e) then begin
    Err('cannot add header field ' + path);
    Exit;
  end;
  SetEditValue(e, StringReplace(v, '\n', #13#10, [rfReplaceAll]));
end;

procedure OpUnref(edid, cellId: string);
var
  cell, r: IInterface;
begin
  cell := FindAny(cellId);
  if not Assigned(cell) then
    Exit;
  r := FindInGroup(ChildGroup(InCur(cell)), edid, True);
  if Assigned(r) then begin
    Remove(r);
    log.Add('removed ' + edid);
  end;
end;

procedure OpItems(edid, list: string);
var
  r, items, it: IInterface;
  sl: TStringList;
  i, p: integer;
  t: string;
begin
  r := Rec(edid);
  if not Assigned(r) then
    Exit;
  r := InCur(r);
  RemoveElement(r, 'Items');
  RemoveElement(r, 'COCT');
  sl := TStringList.Create;
  sl.Delimiter := ';';
  sl.StrictDelimiter := True;
  sl.DelimitedText := list;
  items := Add(r, 'Items', True);
  for i := 0 to sl.Count - 1 do begin
    t := Trim(sl[i]);
    if t = '' then
      Continue;
    p := Pos('*', t);
    if i = 0 then
      it := ElementByIndex(items, 0)
    else
      it := ElementAssign(items, HighInteger, nil, False);
    SetElementEditValues(it, 'CNTO\Item', Value(Copy(t, 1, p - 1)));
    SetElementEditValues(it, 'CNTO\Count', Copy(t, p + 1, Length(t)));
  end;
  log.Add(Format('%s: %d items', [edid, ElementCount(items)]));
  sl.Free;
end;

procedure OpMenuClear(edid: string);
var
  r: IInterface;
begin
  r := Rec(edid);
  if Assigned(r) then begin
    r := InCur(r);
    RemoveElement(r, 'Menu Items');
    RemoveElement(r, 'ISIZ');
  end;
end;

procedure OpMenu(edid, id, text, sub, cond: string);
var
  r, items, it, c, conds, tmpl: IInterface;
  parts: TStringList;
begin
  r := Rec(edid);
  if not Assigned(r) then
    Exit;
  r := InCur(r);
  // xEdit cannot add conditions to a new menu item (assertion failure), so an item with a condition starts as
  // a copy of a vanilla one that has them (MenuTemplate's second item), cut down to a single condition.
  tmpl := nil;
  if cond <> '-' then
    tmpl := ElementByIndex(ElementByPath(FindAny(MenuTemplate), 'Menu Items'), 1);
  items := ElementByPath(r, 'Menu Items');
  if Assigned(items) then
    it := ElementAssign(items, HighInteger, tmpl, False)
  else begin
    items := Add(r, 'Menu Items', True);
    it := ElementByIndex(items, 0);
    if Assigned(tmpl) then
      it := ElementAssign(items, 0, tmpl, False);
  end;
  if cond <> '-' then begin
    conds := ElementByPath(it, 'Conditions');
    while ElementCount(conds) > 1 do
      Remove(ElementByIndex(conds, 1));
    RemoveElement(ElementByIndex(conds, 0), 'CIS2');
    RemoveElement(it, 'RNAM');
    RemoveElement(it, 'UNAM');
    RemoveElement(it, 'VNAM');
    RemoveElement(it, 'TNAM');
  end;
  SetElementEditValues(it, 'ITXT', text);
  SetElementEditValues(it, 'ITID', id);
  if sub <> '-' then begin
    SetElementEditValues(it, 'ANAM', 'Submenu - Terminal');
    Ensure(it, 'TNAM');
    SetElementEditValues(it, 'TNAM', Value(sub));
  end
  else
    // runs the item's script event and shows the same menu again, ready for the next choice
    SetElementEditValues(it, 'ANAM', 'Submenu - Force Redraw');
  if cond <> '-' then begin
    parts := TStringList.Create;
    parts.Delimiter := ':';
    parts.StrictDelimiter := True;
    parts.DelimitedText := cond;
    c := ElementByIndex(ElementByPath(it, 'Conditions'), 0);
    if not Assigned(c) then begin
      Err('cannot add a condition to ' + edid + ' item ' + id);
      parts.Free;
      Exit;
    end;
    SetElementEditValues(c, 'CTDA\Function', parts[0]);  // first: it decides the parameter types
    SetElementEditValues(c, 'CTDA\Type', '10000000');
    SetElementEditValues(c, 'CTDA\Comparison Value', parts[2]);
    SetElementEditValues(c, 'CTDA\Parameter #1', Value(parts[1]));
    SetElementEditValues(c, 'CTDA\Run On', 'Reference');
    SetElementEditValues(c, 'CTDA\Reference', '00000014');
    parts.Free;
  end;
end;

function ScriptEntry(r: IInterface; scriptName: string): IInterface;
var
  scripts: IInterface;
  i: integer;
begin
  Result := nil;
  scripts := ElementByPath(r, 'VMAD\Scripts');
  for i := 0 to ElementCount(scripts) - 1 do
    if SameText(GetElementEditValues(ElementByIndex(scripts, i), 'ScriptName'), scriptName) then
      Result := ElementByIndex(scripts, i);
end;

procedure OpScript(edid, scriptName: string);
var
  r, scripts, s: IInterface;
begin
  r := Rec(edid);
  if not Assigned(r) then
    Exit;
  r := InCur(r);
  if not Assigned(ScriptEntry(r, scriptName)) then begin
    if not Assigned(ElementByPath(r, 'VMAD')) then
      Add(r, 'VMAD', True);
    scripts := ElementByPath(r, 'VMAD\Scripts');
    s := ElementAssign(scripts, HighInteger, nil, False);
    SetElementEditValues(s, 'ScriptName', scriptName);
  end;
  // a new VMAD comes with an empty fragment block; these scripts use events, not fragments. Quests must keep
  // theirs (the CK rejects a quest VMAD without its fragment header).
  if Signature(r) <> 'QUST' then
    RemoveElement(ElementByPath(r, 'VMAD'), 'Script Fragments');
  if not Assigned(ScriptEntry(r, scriptName)) then
    Err(Format('%s: script %s was not attached (VMAD present %s, %d scripts, record %s)', [edid, scriptName,
      IntToStr(Ord(Assigned(ElementByPath(r, 'VMAD')))), ElementCount(ElementByPath(r, 'VMAD\Scripts')),
      Name(r)]));
end;

procedure OpPropRemove(edid, scriptName, propName: string);
var
  r, s, props: IInterface;
  i: integer;
begin
  r := Rec(edid);
  if not Assigned(r) then
    Exit;
  r := InCur(r);
  s := ScriptEntry(r, scriptName);
  if not Assigned(s) then
    Exit;
  props := ElementByPath(s, 'Properties');
  for i := ElementCount(props) - 1 downto 0 do
    if SameText(GetElementEditValues(ElementByIndex(props, i), 'propertyName'), propName) then begin
      RemoveElement(props, i);
      log.Add('removed property ' + edid + '.' + propName);
    end;
end;

procedure OpProp(edid, scriptName, propName, typ, v: string);
var
  r, s, props, p, arr, el: IInterface;
  i: integer;
  sl: TStringList;
begin
  r := Rec(edid);
  if not Assigned(r) then
    Exit;
  r := InCur(r);
  s := ScriptEntry(r, scriptName);
  if not Assigned(s) then begin
    Err(edid + ' has no script ' + scriptName);
    Exit;
  end;
  props := ElementByPath(s, 'Properties');
  if not Assigned(props) then
    props := Add(s, 'Properties', True);
  p := nil;
  for i := 0 to ElementCount(props) - 1 do
    if SameText(GetElementEditValues(ElementByIndex(props, i), 'propertyName'), propName) then
      p := ElementByIndex(props, i);
  if not Assigned(p) then
    p := ElementAssign(props, HighInteger, nil, False);
  SetElementEditValues(p, 'propertyName', propName);
  SetElementEditValues(p, 'Type', typ);
  if typ = 'Object' then begin
    SetElementEditValues(p, 'Value\Object Union\Object v2\FormID', Value(v));
    if GetNativeValue(ElementByPath(p, 'Value\Object Union\Object v2\FormID')) = 0 then
      Err(edid + '.' + propName + ': ' + v + ' did not resolve');
  end
  else if typ = 'Array of Object' then begin
    arr := ElementByPath(p, 'Value\Array of Object');
    while ElementCount(arr) > 0 do
      RemoveElement(arr, 0);
    sl := TStringList.Create;
    sl.Delimiter := ',';
    sl.StrictDelimiter := True;
    sl.DelimitedText := v;
    for i := 0 to sl.Count - 1 do begin
      // the new element is the Object Union itself
      el := ElementAssign(arr, HighInteger, nil, False);
      SetElementEditValues(el, 'Object v2\FormID', Value(Trim(sl[i])));
      if GetNativeValue(ElementByPath(el, 'Object v2\FormID')) = 0 then
        Err(edid + '.' + propName + '[' + IntToStr(i) + ']: ' + Trim(sl[i]) + ' did not resolve');
    end;
    sl.Free;
  end
  else begin
    // a scalar's value sits directly on the property (Value = ...), not under a Value\<type> node
    SetElementEditValues(p, 'Value', v);
    if (typ <> 'String') and (StrToFloatDef(GetElementEditValues(p, 'Value'), -1e30) <> StrToFloatDef(v, 1e30))
      and not SameText(GetElementEditValues(p, 'Value'), v) then
      Err(Format('%s.%s: asked %s, got %s', [edid, propName, v, GetElementEditValues(p, 'Value')]));
  end;
end;

// Give records whose object ID is past an ESL's 0xFFF a free ID inside the range, repointing everything that
// refers to them. The Creation Kit numbers new navmeshes from its own counter (0x15D8 once), and Compact Active
// File Form IDs does not always catch them; xEdit then refuses to save the ESL.
function FirstOutOfRange(f: IInterface): IInterface;
var
  i: integer;
  e: IInterface;
begin
  Result := nil;
  for i := 0 to RecordCount(f) - 1 do begin
    e := RecordByIndex(f, i);
    if IsMaster(e) and Equals(GetFile(e), f) and ((FormID(e) and $FFFFFF) > $FFF) then begin
      Result := e;
      Exit;
    end;
  end;
end;

procedure FixOutOfRangeIDs(f: IInterface);
var
  i, j, id, free: integer;
  e, user: IInterface;
  used: TStringList;
  oldID, newID: cardinal;
begin
  used := TStringList.Create;
  used.Sorted := True;
  for i := 0 to RecordCount(f) - 1 do begin
    e := RecordByIndex(f, i);
    if IsMaster(e) and Equals(GetFile(e), f) then
      used.Add(IntToHex(FormID(e) and $FFFFFF, 6));
  end;
  free := $800;
  // one at a time, rescanning: renumbering re-sorts the file's records, so indexes shift under a loop
  e := FirstOutOfRange(f);
  while Assigned(e) do begin
    id := FormID(e) and $FFFFFF;
    while used.IndexOf(IntToHex(free, 6)) >= 0 do
      Inc(free);
    if free > $FFF then begin
      Err(GetFileName(f) + ': no free ESL object ID left for ' + Name(e));
      Break;
    end;
    oldID := GetLoadOrderFormID(e);
    newID := (oldID and $FFFFF000) or free;  // a light plugin keeps its slot in bits 12-23
    for j := ReferencedByCount(e) - 1 downto 0 do begin
      user := ReferencedByIndex(e, j);
      CompareExchangeFormID(user, oldID, newID);
    end;
    SetLoadOrderFormID(e, newID);
    used.Add(IntToHex(free, 6));
    log.Add(Format('%s: renumbered %s [%x] to %x', [GetFileName(f), Signature(e), id, free]));
    e := FirstOutOfRange(f);
  end;
  used.Free;
end;

// Point the header's next object ID just past the highest ID in use. The CK hands out new IDs from it, and an
// ESL must stay within 0xFFF (a CK-generated navmesh once got 0x1010 from a stale counter).
procedure FixNextObjectID(f: IInterface);
var
  i, id, top: integer;
  e: IInterface;
begin
  top := $800;
  for i := 0 to RecordCount(f) - 1 do begin
    e := RecordByIndex(f, i);
    if IsMaster(e) and Equals(GetFile(e), f) then begin
      id := FormID(e) and $FFFFFF;
      if id >= top then
        top := id + 1;
    end;
  end;
  SetElementNativeValues(ElementByIndex(f, 0), 'HEDR\Next Object ID', top);
  log.Add(Format('%s: next object ID %x', [GetFileName(f), top]));
end;

function Initialize: integer;
var
  spec, done: TStringList;
  i: integer;
  line, op: string;
begin
  nOk := 0;
  nErr := 0;
  log := TStringList.Create;
  cache := TStringList.Create;
  refIdx := TStringList.Create;
  touched := TStringList.Create;
  built := TStringList.Create;
  made := TStringList.Create;
  touched.Sorted := True;
  touched.Duplicates := dupIgnore;
  spec := TStringList.Create;
  spec.LoadFromFile(SpecFile);
  cur := FileByName(TargetFile);
  for i := 0 to spec.Count - 1 do begin
    line := spec[i];
    if (Trim(line) = '') or (Copy(Trim(line), 1, 1) = '#') then
      Continue;
    op := Field(line, 0);
    if op = 'file' then OpFile(Field(line, 1))
    else if op = 'master' then AddMasterIfMissing(cur, Field(line, 1))
    else if op = 'header' then OpHeader(Field(line, 1), Field(line, 2))
    else if op = 'copy' then OpCopy(Field(line, 1), Field(line, 2))
    else if op = 'new' then OpNew(Field(line, 1), Field(line, 2))
    else if op = 'set' then OpSet(Field(line, 1), Field(line, 2), Field(line, 3))
    else if op = 'remove' then OpRemove(Field(line, 1), Field(line, 2))
    else if op = 'ref' then OpRef(Field(line, 1), Field(line, 2), Field(line, 3), Field(line, 4), Field(line, 5), Field(line, 6))
    else if op = 'unref' then OpUnref(Field(line, 1), Field(line, 2))
    else if op = 'prune' then OpPrune(Field(line, 1), Field(line, 2))
    else if op = 'prunerecords' then OpPruneRecords(Field(line, 1))
    else if op = 'items' then OpItems(Field(line, 1), Field(line, 2))
    else if op = 'menuclear' then OpMenuClear(Field(line, 1))
    else if op = 'menu' then OpMenu(Field(line, 1), Field(line, 2), Field(line, 3), Field(line, 4), Field(line, 5))
    else if op = 'script' then OpScript(Field(line, 1), Field(line, 2))
    else if op = 'propremove' then OpPropRemove(Field(line, 1), Field(line, 2), Field(line, 3))
    else if op = 'prop' then OpProp(Field(line, 1), Field(line, 2), Field(line, 3), Field(line, 4), Field(line, 5))
    else
      Err('unknown operation on line ' + IntToStr(i + 1) + ': ' + line);
    Inc(nOk);
    if i mod 50 = 0 then begin
      log.SaveToFile(OutDir + 'result.txt');
    end;
  end;
  for i := 0 to FileCount - 1 do
    if built.IndexOf(GetFileName(FileByIndex(i))) >= 0 then begin
      FixOutOfRangeIDs(FileByIndex(i));
      FixNextObjectID(FileByIndex(i));
    end;
  log.Insert(0, Format('%d operations, %d errors', [nOk, nErr]));
  log.SaveToFile(OutDir + 'result.txt');
  done := TStringList.Create;
  done.Add('ok');
  done.SaveToFile(OutDir + 'DONE.txt');
  done.Free;
  spec.Free;
  cache.Free;
  log.Free;
  Result := 0;
end;

end.
