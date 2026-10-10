{
  AgentCreationKit: apply a list of record edits from a text file (the EDITS parameter) to the target plugin.

  One edit per line, fields separated by " | ". Blank lines and lines starting with # are ignored.
  Every edit must match exactly one thing; anything that does not match is reported as ERROR and skipped.

    prop.set     | OMOD_EDID | PROPERTY[key]#n | FUNCTION | VALUE   change a property's function type and value
    prop.remove  | OMOD_EDID | PROPERTY[key]#n                        delete a property
    prop.add     | OMOD_EDID | PROPERTY | FUNCTION | VALUE | TEMPLATE_OMOD_EDID [| KEY_VALUE]
                   add a property, cloned from the first PROPERTY entry on TEMPLATE (gives the right value type);
                   KEY_VALUE sets Value 1 for keyed properties such as DamageTypeValues (e.g. dtCryo)
    text.set     | EDID | PATH | NEW TEXT                             set a string field (FULL, DESC, ...)
    text.replace | EDID | PATH | OLD | NEW                            replace a substring in a string field
    effect.remove    | ENCH/SPEL_EDID | INDEX                         remove effect #INDEX (0-based)
    effect.magnitude | ENCH/SPEL_EDID | INDEX | VALUE                 set effect #INDEX's magnitude
    menu.set     | TERM_EDID | ITEM_ID | FIELD | NEW TEXT             set a terminal menu item's ITXT (label),
                   RNAM (response) or UNAM (display text)
    rec.copy     | SOURCE_EDID | NEW_EDID                             copy a record (from the target or any master)
                   into the target as a new record; skipped if NEW_EDID already exists
    field.set    | EDID | PATH | VALUE                                set any field by xEdit path, e.g.
                   Effects\[1]\EFID or Magic Effect Data\DATA\Perk to Apply. VALUE @SOME_EDID is
                   replaced by that record's FormID

  PROPERTY[key]#n selects the n-th (1-based, default 1) property with that name; [key] filters on Value 1,
  e.g. DamageTypeValues[dtEnergy]#2. VALUE goes to Value 2 for "FormID,Float"/"FormID,Int" properties
  (keyed ones) and to Value 1 otherwise.
}
unit ACKApplyEdits;

const
  TargetFile = '{{TARGET}}';
  OutDir = '{{OUT}}';
  EditsFile = '{{EDITS}}';

var
  log: TStringList;
  f: IInterface;
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

function FindIn(fl: IInterface; edid: string): IInterface;
var
  i: integer;
  g: IInterface;
begin
  Result := nil;
  for i := 0 to ElementCount(fl) - 1 do begin
    g := ElementByIndex(fl, i);
    if Signature(g) = 'GRUP' then begin
      Result := MainRecordByEditorID(g, edid);
      if Assigned(Result) then
        Exit;
    end;
  end;
end;

function FindRec(edid: string): IInterface;
begin
  Result := FindIn(f, edid);
end;

function FindAny(edid: string): IInterface;
var
  i: integer;
begin
  Result := FindRec(edid);
  for i := FileCount - 1 downto 0 do begin
    if Assigned(Result) then
      Exit;
    Result := FindIn(FileByIndex(i), edid);
  end;
end;

function Resolve(value: string): string;
var
  r: IInterface;
begin
  Result := value;
  if Copy(value, 1, 1) = '@' then begin
    r := FindAny(Copy(value, 2, Length(value)));
    if Assigned(r) then
      Result := IntToHex(GetLoadOrderFormID(r), 8)
    else
      Result := '';
  end;
end;

function Fail(line, msg: string): boolean;
begin
  log.Add('ERROR  ' + msg + '   <- ' + line);
  Inc(nErr);
  Result := False;
end;

procedure Ok(line, msg: string);
begin
  log.Add('ok     ' + msg + '   <- ' + line);
  Inc(nOk);
end;

function PropDesc(p: IInterface): string;
begin
  Result := GetElementEditValues(p, 'Property') + ' ' + GetElementEditValues(p, 'Function Type') + ' ' +
    GetElementEditValues(p, 'Value 1') + ' / ' + GetElementEditValues(p, 'Value 2');
end;

function SelectProp(omod: IInterface; spec: string): IInterface;
var
  props, p: IInterface;
  name, key: string;
  want, seen, i, b: integer;
begin
  Result := nil;
  want := 1;
  i := Pos('#', spec);
  if i > 0 then begin
    want := StrToInt(Copy(spec, i + 1, Length(spec)));
    spec := Copy(spec, 1, i - 1);
  end;
  key := '';
  b := Pos('[', spec);
  if b > 0 then begin
    key := Copy(spec, b + 1, Pos(']', spec) - b - 1);
    spec := Copy(spec, 1, b - 1);
  end;
  name := spec;
  seen := 0;
  props := ElementByPath(omod, 'DATA\Properties');
  for i := 0 to ElementCount(props) - 1 do begin
    p := ElementByIndex(props, i);
    if GetElementEditValues(p, 'Property') <> name then
      Continue;
    if (key <> '') and (Pos(key, GetElementEditValues(p, 'Value 1')) <> 1) then
      Continue;
    Inc(seen);
    if seen = want then begin
      Result := p;
      Exit;
    end;
  end;
end;

procedure SetPropValue(p: IInterface; func, value: string);
begin
  SetElementEditValues(p, 'Function Type', func);
  if Pos('FormID,', GetElementEditValues(p, 'Value Type')) = 1 then
    SetElementEditValues(p, 'Value 2', value)
  else
    SetElementEditValues(p, 'Value 1', value);
end;

function Effects(rec: IInterface): IInterface;
begin
  Result := ElementByName(rec, 'Effects');
end;

procedure Apply(line: string);
var
  op, edid, a, b, c, d, before: string;
  rec, p, tmpl, effs, items, item: IInterface;
  i: integer;
begin
  op := Field(line, 0);
  edid := Field(line, 1);
  a := Field(line, 2);
  b := Field(line, 3);
  c := Field(line, 4);
  d := Field(line, 5);
  if op = 'rec.copy' then begin
    if Assigned(FindRec(a)) then begin
      Ok(line, 'already present: ' + a);
      Exit;
    end;
    rec := FindAny(edid);
    if not Assigned(rec) then begin
      Fail(line, 'source record not found: ' + edid);
      Exit;
    end;
    p := wbCopyElementToFile(rec, f, True, True);
    SetEditorID(p, a);
    Ok(line, 'copied ' + Name(rec) + ' as ' + Name(p));
    Exit;
  end;
  rec := FindRec(edid);
  if not Assigned(rec) then begin
    Fail(line, 'record not found: ' + edid);
    Exit;
  end;

  if op = 'prop.set' then begin
    p := SelectProp(rec, a);
    if not Assigned(p) then begin
      Fail(line, 'property not found: ' + a);
      Exit;
    end;
    before := PropDesc(p);
    SetPropValue(p, b, c);
    Ok(line, before + '  =>  ' + PropDesc(p));
  end
  else if op = 'prop.remove' then begin
    p := SelectProp(rec, a);
    if not Assigned(p) then begin
      Fail(line, 'property not found: ' + a);
      Exit;
    end;
    before := PropDesc(p);
    RemoveElement(ElementByPath(rec, 'DATA\Properties'), p);
    Ok(line, 'removed ' + before);
  end
  else if op = 'prop.add' then begin
    tmpl := SelectProp(FindRec(d), a);
    if not Assigned(tmpl) then begin
      Fail(line, 'template property ' + a + ' not found on ' + d);
      Exit;
    end;
    p := ElementAssign(ElementByPath(rec, 'DATA\Properties'), HighInteger, tmpl, False);
    if Field(line, 6) <> '' then
      SetElementEditValues(p, 'Value 1', Field(line, 6));
    SetPropValue(p, b, c);
    Ok(line, 'added ' + PropDesc(p));
  end
  else if op = 'text.set' then begin
    before := GetElementEditValues(rec, a);
    SetElementEditValues(rec, a, b);
    Ok(line, a + ': "' + before + '"  =>  "' + GetElementEditValues(rec, a) + '"');
  end
  else if op = 'text.replace' then begin
    before := GetElementEditValues(rec, a);
    if Pos(b, before) = 0 then begin
      Fail(line, a + ' does not contain "' + b + '": "' + before + '"');
      Exit;
    end;
    SetElementEditValues(rec, a, StringReplace(before, b, c, [rfReplaceAll]));
    Ok(line, a + ': "' + GetElementEditValues(rec, a) + '"');
  end
  else if (op = 'effect.remove') or (op = 'effect.magnitude') then begin
    effs := Effects(rec);
    i := StrToInt(a);
    if (not Assigned(effs)) or (i >= ElementCount(effs)) then begin
      Fail(line, 'effect #' + a + ' not found');
      Exit;
    end;
    p := ElementByIndex(effs, i);
    before := GetElementEditValues(p, 'EFID') + ' mag ' + GetElementEditValues(p, 'EFIT\Magnitude');
    if op = 'effect.remove' then begin
      RemoveElement(effs, p);
      Ok(line, 'removed effect ' + before);
    end
    else begin
      SetElementEditValues(p, 'EFIT\Magnitude', b);
      Ok(line, before + '  =>  mag ' + GetElementEditValues(p, 'EFIT\Magnitude'));
    end;
  end
  else if op = 'menu.set' then begin
    items := ElementByName(rec, 'Menu Items');
    for i := 0 to ElementCount(items) - 1 do begin
      item := ElementByIndex(items, i);
      if GetElementEditValues(item, 'ITID') = a then begin
        before := GetElementEditValues(item, b);
        SetElementEditValues(item, b, c);
        Ok(line, 'item ' + a + ' ' + b + ': "' + before + '"  =>  "' + GetElementEditValues(item, b) + '"');
        Exit;
      end;
    end;
    Fail(line, 'menu item ' + a + ' not found');
  end
  else if op = 'field.set' then begin
    p := ElementByPath(rec, a);
    if not Assigned(p) then begin
      Fail(line, 'field not found: ' + a);
      Exit;
    end;
    c := Resolve(b);
    if c = '' then begin
      Fail(line, 'reference not found: ' + b);
      Exit;
    end;
    before := GetEditValue(p);
    SetEditValue(p, c);
    Ok(line, a + ': "' + before + '"  =>  "' + GetEditValue(p) + '"');
  end
  else
    Fail(line, 'unknown operation ' + op);
end;

function Initialize: integer;
var
  i: integer;
  lines, done: TStringList;
  line: string;
begin
  log := TStringList.Create;
  lines := TStringList.Create;
  nErr := 0;
  nOk := 0;
  for i := 0 to FileCount - 1 do
    if GetFileName(FileByIndex(i)) = TargetFile then
      f := FileByIndex(i);
  if not Assigned(f) then
    log.Add('ERROR  target plugin not loaded')
  else begin
    lines.LoadFromFile(EditsFile);
    for i := 0 to lines.Count - 1 do begin
      line := Trim(lines[i]);
      if (line <> '') and (Copy(line, 1, 1) <> '#') then
        Apply(line);
    end;
  end;
  log.Insert(0, Format('%d edits applied, %d errors', [nOk, nErr]));
  log.SaveToFile(OutDir + 'result.txt');
  done := TStringList.Create;
  done.Add('ok');
  done.SaveToFile(OutDir + 'DONE.txt');
  done.Free;
  lines.Free;
  log.Free;
  Result := 0;
end;

end.
