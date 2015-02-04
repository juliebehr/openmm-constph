from lxml import etree
import copy

class XMLmodifier(Object):
    def __init__(self, ffxml_filename, each_molecule_N):
        """
        """
        self.ffxml_filename = ffxml_filename
        self.each_molecule_N = each_molecule_N
        self.tree = etree.parse(ffxml_filename)
        self.root = self.tree.getroot()

        root = self.root
        for element in list(root):
            if element.tag == 'AtomTypes':
                self.atomtypes = element
            elif element.tag == 'Residues':
                self.residues = element
            elif element.tag == 'HarmonicBondForce':
                self.bondforce = element
            elif element.tag == 'HarmonicAngleForce':
                self.angleforce = element
            elif element.tag == 'PeriodicTorsionForce':
                self.torsionforce = element
            elif element.tag == 'NonbondedForce':
                self.nonbonded = element

        self.fixatomtypes()
        self.addbondforces()
        self.addcustomforces()

        new_filename = ffxml_filename[:-4]+"_MODIFIED.xml"
        self.tree.write(new_filename)



    def fixatomtypes(self):
        atomtypes = self.atomtypes
        each_molecule_N = self.each_molecule_N
        # make each_molecule_N a dictionary mapping from the index of an atom in the dual
        # topology to an id # representing the molecule it originates from
        # (I'm not sure if this is more useful in general, if so it can be changed when
        # created instead of here)
        # dict {index of atom : index of molecule it comes from}
        molecule_id_of_atom = {}
        for i, start_end_indices in enumerate(each_molecule_N):
            start_index = start_end_indices[0]
            end_index = start_end_indices[1]+1
            for j in range(start_index, end_index):
                molecule_id_of_atom[j] = i

        self.substructure_length = each_molecule_N[0][1]
        self.molecule_id_of_atom = molecule_id_of_atom
        

        save_index_to_class = {}
        save_real_classes = {}

        # modify the atom class of atoms unique to certain ligands 
        # COMPLETE
        for i, atom in enumerate(list(atomtypes)):
            # atoms in the substructure do not change and therefore don't need
            # to be customized
            real_class_name = atom.attrib['class']
            if i > substructure_length:
                molecule_id = str(molecule_id_of_atom[i])
                modified_class_name = real_class_name+'_'+molecule_id
                atom.attrib['class'] = modified_class_name
            else:
                modified_class_name = real_class_name
            save_index_to_class[i] = modified_class_name
            save_real_classes[modified_class_name] = real_class_name

        self.save_index_to_class = save_index_to_class
        self.save_real_classes = save_real_classes


    def addbondforces(self):
        root = self.root
        residues = self.residues
        save_index_to_class = self.save_index_to_class
        save_real_classes = self.save_real_classes

        # add entries to harmonic bond force with modified atom classes
        # COMPLETE
        for residue in list(residues):
            for element in list(residue):
                if element.tag == 'Bond':
                    atom1 = element.values()[0]
                    atom2 = element.values()[1]
                    newclass1 = save_index_to_class[atom1]
                    newclass2 = save_index_to_class[atom2]
                    oldclass1 = save_real_classes[newclass1]
                    oldclass2 = save_real_classes[newclass2]
                    if newclass1 == oldclass1 and newclass2 == oldclass2:
                        continue
                    # THIS IS MAD COOL
                    bond = root.xpath(u'//Bond[@class1=\'%s\'][@class2=\'%s\']' %(oldclass1, oldclass2))
                    if bond == []:
                        bond = root.xpath(u'//Bond[@class1=\'%s\'][@class2=\'%s\']' %(oldclass2, oldclass1))
                    bond = bond[0]
                    newbond = copy.deepcopy(bond)
                    newbond.attrib['class1'] = newclass1
                    newbond.attrib['class2'] = newclass2
                    bond.addnext(newbond)


    def addcustomforces(self):
        each_molecule_N = self.each_molecule_N

        for i, start_end_indices in enumerate(each_molecule_N):
        # did this need to be enumerated?
            if i == 0:
                continue
            start_index = start_end_indices[0]
            end_index = start_end_indices[1]+1

            molecule_atom_indices = range(self.substructure_length+1)
            molecule_atom_indices.extend(range(start_index, end_index)
            scale_factor = "lambda"+str(i)
            self.customangleforce(scale_factor, molecule_atom_indices)
            self.customtorsionforce(scale_factor, molecule_atom_indices)
            self.customnonbondedforce(scale_factor, molecule_atom_indices)

    def customangleforce(self, scale_factor, molecule_atom_indices):
        angleforce = self.angleforce
        save_index_to_class = self.save_index_to_class
        save_real_classes = self.save_real_classes

        # create the custom angle force element
        custom_angle_force = copy.deepcopy(angleforce)
        custom_angle_force.tag = 'CustomAngleForce'
        custom_angle_force.attrib['energy'] = scale_factor+"*k*(theta-angle)^2" # this can't be scale though it has to be a variable somehow?

        # add subelements for the parameters
        angle = custom_angle_force.makeelement('PerAngleParameter',attrib={'name':"angle"})
        custom_angle_force.insert(0,angle)
        k = custom_angle_force.makeelement('PerAngleParameter',attrib={'name':"k"})
        custom_angle_force.insert(0,k)
        scale = custom_angle_force.makeelement('GlobalParameter',attrib={ 'name':scale_factor, 'defaultValue':"0.5"}) # lambda is a python thing already?
        custom_angle_force.insert(0,scale)

        for atom1 in molecule_atom_indices:
            newclass1 = save_index_to_class[atom1]
            oldclass1 = save_real_classes[newclass1]
            for atom2 in molecule_atom_indices:
                if atom2 == atom1:
                    continue # just realized it's actually probably easy to pick out real angles
                newclass2 = save_index_to_class[atom2]
                oldclass2 = save_real_classes[newclass2]
                for atom3 in molecule_atom_indices:
                    if atom3 == atom1 or atom3 == atom2:
                        continue
                    newclass3 = save_index_to_class[atom3]
                    oldclass3 = save_real_classes[newclass3]
                    if newclass1 == oldclass1 and newclass2 == oldclass2 and newclass3 == oldclass3:
                        continue
                    # find the parameters for the original three atom classes
                    angle = root.xpath(u'//Angle[@class1=\'%s\'][@class2=\'%s\'][@class3=\'%s\']' %(oldclass1, oldclass2, oldclass3))
                    if angle == []:
                        angle = root.xpath(u'//Angle[@class1=\'%s\'][@class2=\'%s\'][@class3=\'%s\']' %(oldclass3, oldclass2, oldclass1))
                    if angle == []:
                        continue
                    angle = angle[0]
                    newangle = copy.deepcopy(angle)
                    newangle.attrib['class1'] = newclass1
                    newangle.attrib['class2'] = newclass2
                    newangle.attrib['class3'] = newclass3
                    if newclass1 != oldclass1 and newclass2 != oldclass2 and newclass3 != oldclass3:
                        # add to regular angleforce
                        angle.addnext(newangle)
                    else
                        # add to custom_angle_force
                        custom_angle_force.append(newbond)

        angleforce.addprevious(custom_angle_force)


    def customtorsionforce(self, scale_factor, molecule_atom_indices):
        torsionforce = self.torsionforce

        # create the custom torsion
        custom_torsion_force = copy.deepcopy(torsionforce)
        custom_torsion_force.tag = 'CustomTorsionForce'
        custom_torsion_force.attrib['energy'] = scale_factor+"*k*(1+cos(periodicity*theta-phase))"



        torsionforce.addprevious(custom_torsion_force)



    def customnonbondedforce(self, scale_factor, molecule_atom_indices):
        nonbonded = self.nonbonded

        # create the custom nonbonded force element
        custom_nonbonded_force = copy.deepcopy(nonbonded)
        custom_nonbonded_force.tag = 'CustomNonbondedForce'
        # I don't know what the energy expression is

        # assuming the energy expression gets in there right this is g2g:
        for idx, nonbonded_particle in enumerate(list(custom_nonbonded_force)):
            if idx > substructure_length:
                if idx not in range(start_index, end_index):
                    custom_nonbonded_force.remove(nonbonded_particle)
        nonbonded.addprevious(custom_nonbonded_force)












