{
  AgentCreationKit: every navmesh (NAVM) of the target plugin, for checking a generated navmesh without the
  Creation Kit. Read-only. Writes navmesh.tsv, one line per item:
    V  NAVM-ID  x y z            a vertex
    E  NAVM-ID  text             an edge link (a triangle edge joined to another navmesh)
    D  NAVM-ID  text             a door triangle
  python -m ack navmesh summarises it (bounds per navmesh, links between them).
}
unit ACKNavmeshDump;

const
  TargetFile = '{{TARGET}}';
  OutDir = '{{OUT}}';

procedure AddAll(sl: TStringList; kind, id: string; list: IInterface);
var
  i, j: integer;
  e: IInterface;
  s: string;
begin
  for i := 0 to ElementCount(list) - 1 do begin
    e := ElementByIndex(list, i);
    s := GetEditValue(e);
    for j := 0 to ElementCount(e) - 1 do
      s := s + ' ' + Name(ElementByIndex(e, j)) + '=' + GetEditValue(ElementByIndex(e, j));
    sl.Add(kind + #9 + id + #9 + s);
  end;
end;

function Initialize: integer;
var
  i, j: integer;
  f, r, verts, v: IInterface;
  sl: TStringList;
  id: string;
begin
  sl := TStringList.Create;
  for i := 0 to FileCount - 1 do
    if SameText(GetFileName(FileByIndex(i)), TargetFile) then
      f := FileByIndex(i);
  for i := 0 to RecordCount(f) - 1 do begin
    r := RecordByIndex(f, i);
    if (Signature(r) <> 'NAVM') or not IsMaster(r) then
      Continue;
    id := IntToHex(FormID(r), 8);
    verts := ElementByPath(r, 'NVNM\Vertices');
    for j := 0 to ElementCount(verts) - 1 do begin
      v := ElementByIndex(verts, j);
      if ElementCount(v) >= 3 then
        sl.Add('V' + #9 + id + #9 + GetEditValue(ElementByIndex(v, 0)) + ' ' + GetEditValue(ElementByIndex(v, 1)) +
          ' ' + GetEditValue(ElementByIndex(v, 2)))
      else
        sl.Add('V' + #9 + id + #9 + 'raw ' + GetEditValue(v));
    end;
    AddAll(sl, 'E', id, ElementByPath(r, 'NVNM\Edge Links'));
    AddAll(sl, 'D', id, ElementByPath(r, 'NVNM\Door Triangles'));
  end;
  sl.SaveToFile(OutDir + 'navmesh.tsv');
  sl.Clear;
  sl.Add('ok');
  sl.SaveToFile(OutDir + 'DONE.txt');
  sl.Free;
  Result := 0;
end;

end.
