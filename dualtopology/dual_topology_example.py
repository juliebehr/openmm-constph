import oetopologytools

l1 = "c1c(O)c(O)c(Cl)cc1CCCBr"
l2 = "c1cc(O)c(O)cc1CCN"
ligands = [l1,l2]

dualtop = oetopologytools.DualTopology(ligands)
dualtop.createDualTopology()

for atom in dualtop.dual_topology.GetAtoms():
    print(atom)
for bond in dualtop.dual_topology.GetBonds():
    print(bond)
print(dualtop.each_molecule_N)

pdb_filename = "dopamine.pdb"
dualtop.savePDBandFFXML(pdb_filename=pdb_filename)



