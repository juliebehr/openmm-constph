import openeye.oechem as oechem
import numpy as np
import gaff2xml.openeye
import os
from trustbutverify import cirpy

class DualTopology(object):
    """
    Intended to aid in the creation of dual topologies and corresponding forcefields

    Constructor:
      DualTopology(cas_or_aa, min_atoms=6) 
        Arguments:
          cas_or_aa (list of strings) molecules identified by cas number, or amino acid by name to combine into dual topology
        Optional:
          min_atoms (int) the minimum number of common atoms to constitute a substructure match (default: 6)

    Currently has the ability to determine a common substructure, and build a v0.2 dual topology containing
    correct atom types and bonds in one lump (no N1 N2 differentiation).
    Also contains a list of tuples each_molecule_N which describe the first and last index of atoms in the
    combined topology that came from the same original topology
    Can correctly save a .pdb file of dual topology

    Future: Figure out why tf the substructure has an extra atom in it
            Define and save atom classes, because they'll be messed up with additional things bonded to them
            How to create ffxml
                - what structure should the ffxml have
                - logistically how can it be done
            DONE - CHANGED TO CAS FOR NOW: Input type needs to be changed - smiles won't work for amino acids, e.g.
                - Also self.title desperately needs to be changed (the example doesn't have corresponding cas no.)
                - but do amino acids have cas numbers?
                - could either use cas, if amino acids have them and just change the example ligands, or
                - use something else to create an OEMol and just take list of OEMols directly
            Should the ffxml itself be changed, or something else (for instance this object, other) have the titratable 
                information and send it over to openmm
            Fix the generation of .xml - shouldn't be doing that readlines nonsense (it's there now because antechamber tries
                to correct atom types based on what they're bonded to)
            Investigate how this all works with amino acids and their dangling bonds

    Requires:
      openeye.oechem
      gaff2xml
      trustbutverify.cirpy
    """

    def __init__(self, cas_or_aa, min_atoms=6):
        """
        Initialize using cas numbers OR amino acid name
        Requires gaff2xml.openeye and trustbutverify.cirpy

        Arguments
            cas_or_aa (list of strings) either cas number or name of amino acid

        Optional Arguments
            min_atoms (int) - a minimum number of atoms for substructure match (default: 6)
        """

        self.cas_or_aa = cas_or_aa
        self.smiles_strings = []
        self.ligands = []
        for cas in cas_or_aa:
            smiles = cirpy.resolve(cas,'smiles')
            self.smiles_strings.append(smiles)
            ligand = gaff2xml.openeye.smiles_to_oemol(smiles)
            ligand = gaff2xml.openeye.get_charges(ligand, strictStereo=False) 
            self.ligands.append(ligand)
        self.title = self.cas_or_aa[0]+"_and_analogs"
        self.min_atoms = min_atoms
        self.common_substructure = None
        self.dual_topology = None
        self.each_molecule_N = []
        self.mapping_dictionaries = []
        self.pdb_filename = None

    def determineCommonSubstructure(self):
        """
        Find a common substructure shared by all ligands.

        The atom type name strings and integer bond types are used to obtain an exact match.

        Will not run if self.common_substructure is not None

        Arguments
          (none)
        """
        if self.common_substructure is not None:
            return
        ligands = self.ligands
        min_atoms = self.min_atoms

        # First, initialize with first ligand.
        common_substructure = ligands[0].CreateCopy() #DLM modification 11/15/10 -- this is how copies should now be made

        atomexpr = oechem.OEExprOpts_DefaultAtoms
        bondexpr = oechem.OEExprOpts_DefaultBonds

        # Now delete bits that don't match every other ligand.
        for ligand in ligands[1:]:
        
            # Create an OEMCSSearch from this molecule.
            mcss = oechem.OEMCSSearch(ligand, atomexpr, bondexpr, oechem.OEMCSType_Exhaustive)

            # ignore substructures smaller than 6 atoms
            mcss.SetMinAtoms(min_atoms)

            # perform match
            for match in mcss.Match(common_substructure):
                nmatched = match.NumAtoms()
            
                # build list of matched atoms in common substructure
                matched_atoms = []
                for matchpair in match.GetAtoms():
                    atom = matchpair.target
                    matched_atoms.append(atom)

                # delete all unmatched atoms from common substructure
                for atom in common_substructure.GetAtoms():
                    if atom not in matched_atoms:
                        common_substructure.DeleteAtom(atom)

                # we only need to consider one match
                break
    
        # return the common substructure
        self.common_substructure = common_substructure

    def createDualTopology(self):
        """
        Create a dual topology combining all ligands into one OEMol sharing as many atoms as possible.
    
        The atom type name strings and integer bond types are used to obtain an exact match.

        Will not run if self.dual_topology is not None.

        Arguments:
          (none)
        """

        if self.dual_topology is not None:
            return
        ligands = self.ligands

        # First, initialize as common substructure.
        self.determineCommonSubstructure()
        common_substructure = self.common_substructure

        # Initialize a dual topology
        dual_topology = common_substructure.CreateCopy()
        min_atoms = common_substructure.NumAtoms()

        self.each_molecule_N.append((0,min_atoms-1))
        new_index = min_atoms-1

        atomexpr = oechem.OEExprOpts_DefaultAtoms
        bondexpr = oechem.OEExprOpts_DefaultBonds

        mcss = oechem.OEMCSSearch(common_substructure, atomexpr, bondexpr, oechem.OEMCSType_Exhaustive)
        mcss.SetMinAtoms(min_atoms)

        # Create intermediate dictionary to translate from atoms in the common substructure to the new 
        # dual topology
        common_to_dual = {}
        for match in mcss.Match(dual_topology):
            for matchpair in match.GetAtoms():
                common_to_dual[matchpair.pattern] = matchpair.target
            break
        # adding this only for index consistency
        self.mapping_dictionaries.append(common_to_dual) 

        # Now add details of each ligand while ignoring non-unique bits.
        for ligand in ligands:
            old_index = new_index
            ligand_to_dual = {}
             
            # perform match
            for match in mcss.Match(ligand):
                nmatched = match.NumAtoms()
            
                # build list of matched atoms in common substructure
                for matchpair in match.GetAtoms():
                    atom = matchpair.target
                    # Use the intermediate dictionary to translate from ligand atoms to corresponding atoms
                    # in the dual topology
                    ligand_to_dual[atom] = common_to_dual[matchpair.pattern]

                # add unique substructure atoms to dual topology
                for atom in ligand.GetAtoms():
                    if atom not in ligand_to_dual.keys():
                        dual_equiv = dual_topology.NewAtom(atom)
                        new_index = dual_equiv.GetIdx()
                        ligand_to_dual[atom] = dual_equiv
                        for bonded_atom in atom.GetAtoms():
                            if bonded_atom in ligand_to_dual.keys():
                                this_bond = ligand.GetBond(atom,bonded_atom)
                                order = this_bond.GetOrder()
                                dual_bonded = ligand_to_dual[bonded_atom]
                                new_bond = dual_topology.NewBond(dual_bonded, dual_equiv)
                                new_bond.SetOrder(order)

                self.mapping_dictionaries.append(ligand_to_dual)
                self.each_molecule_N.append((old_index+1,new_index))
                # we only need to consider one match
                break
    
        # return the common substructure
        self.dual_topology = dual_topology

    def savePDBandFFXML(self, pdb_filename=None, ffxml_filename=None):
        """
        Creates a .pdb file representative of the dual topology and a corresponding .xml file.

        Arguments:
          pdb_filename (optional) the name of the pdb file to save to
          ffxml_filename (optional) the name of the xml file to save to

        Will not overwrite an existing ffxml file with the same file name.

        Requires mdtraj and antechamber
        """
        try:
            import mdtraj as md
        except:
            return

        if pdb_filename is None:
            pdb_filename = self.title+".pdb"
        self.pdb_filename = pdb_filename

        file_prefix = pdb_filename[:-4]

        self.mol2_file = file_prefix+".mol2"

        if ffxml_filename is None:
            ffxml_filename = file_prefix+".xml"
        self.ffxml_filename = ffxml_filename

        self.createDualTopology()

        substructure_pdb = "SUB_" + file_prefix + ".pdb"
        substructure_mol2 = "SUB_" + file_prefix + ".mol2"

        with gaff2xml.utils.enter_temp_directory():
            _unused = gaff2xml.openeye.molecule_to_mol2(self.dual_topology,self.mol2_file)
            _unused = gaff2xml.openeye.molecule_to_mol2(self.common_substructure,substructure_mol2)
            traj = md.load(self.mol2_file)

            print("Run Antechamber")
            # the substructure will work fine and can be run through gaff2xml
            gaff_mol2_SUB = gaff2xml.utils.run_antechamber("SUB_"+file_prefix, substructure_mol2, charge_method=None)[0]
            # the dual topology will have issues and has to be run differently
            gaff_mol2_filename, frcmod_filename = self._run_antechamber(file_prefix, gaff_mol2_SUB, charge_method=None)

            print("Create ffxml file")
            ffxml = gaff2xml.utils.create_ffxml_file([gaff_mol2_filename], [frcmod_filename], override_mol2_residue_name=file_prefix)
        if not os.path.exists(ffxml_filename):
            outfile = open(ffxml_filename, 'w')
            outfile.write(ffxml.read())
            outfile.close()
            ffxml.seek(0)
        traj.save_pdb(pdb_filename)

    def _run_antechamber(self, file_prefix, gaff_mol2_SUB, charge_method=None):
        """
        Called by savePDBandFFXML instead of gaff2xml so that the .gaff.mol2 file can be modified before generating .frcmod
        """
        try:
            from subprocess import getoutput  # If python 3
        except ImportError:
            from commands import getoutput  # If python 2

        gaff_mol2_intermediate = file_prefix + "_int.gaff.mol2"
        gaff_mol2_filename = file_prefix + ".gaff.mol2"
        frcmod_filename = file_prefix + ".frcmod"

        cmd = "antechamber -i %s -fi mol2 -o %s -fo mol2 -s 2" % (self.mol2_file, gaff_mol2_intermediate)
        if charge_method is not None:
            cmd += ' -c %s' % charge_method
        output = getoutput(cmd)

        self._spliceGaffMol2(gaff_mol2_SUB, gaff_mol2_intermediate, gaff_mol2_filename)

        cmd = "parmchk2 -i %s -f mol2 -o %s" % (gaff_mol2_filename, frcmod_filename)
        output = getoutput(cmd)        

        return gaff_mol2_filename, frcmod_filename

    def _spliceGaffMol2(self, old_substructure, old_dualtop, new_dualtop):
        """
        This is an extremely ugly hack but it's easy and it's working

        Arguments:
          old_substructure: a .gaff.mol2 file of the common substructure, which will overwrite
                            the corresponding entries in the dual topology .gaff.mol2 output
          old_dualtop: a .gaff.mol2 file of the dual topology, as it is written by antechamber
          new_dualtop: filename for the new .gaff.mol2 to be written for the dual topology
        """        
        with open(old_substructure, 'r') as fsub:
            with open(old_dualtop, 'r') as fdual:
                with open(new_dualtop, 'w') as fnew:
                    line = fdual.readline()
                    subline = fsub.readline()
                    while not line == '@<TRIPOS>ATOM\n':
                        fnew.write(line)
                        subline = fsub.readline()
                        line = fdual.readline()
                    while not subline == '@<TRIPOS>BOND\n':
                        fnew.write(subline)
                        line = fdual.readline()
                        subline = fsub.readline()
                    while not line == '@<TRIPOS>BOND\n':
                        fnew.write(line)
                        line = fdual.readline()
                    while not subline == '@<TRIPOS>SUBSTRUCTURE\n':
                        fnew.write(subline)
                        line = fdual.readline()
                        subline = fsub.readline()
                    for line in fdual.readlines():
                        fnew.write(line)






